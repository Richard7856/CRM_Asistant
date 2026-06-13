"""
ApprovalService — resolves autonomy levels and creates approval requests.

Two responsibilities:
1. Given (agent, action) → resolve the effective AutonomyLevel by walking
   the policy precedence chain (agent → dept → global → default).
2. Given a level + payload → either create a PENDING request (Level 3),
   record a terminal one (Levels 0/1/2), and return what the executor
   should do next.

Hard rules (cannot be overridden by DB policies):
- DELETE:* → always MANUAL (Level 3)
- No matching policy → MANUAL (Level 3) — safest default, documented
  in DECISIONS.md as a choice we may revisit per Richard's feedback.

The executor consumes this via `check_or_request()` — see
agent_executor.py for the integration point.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.approvals.models import (
    ApprovalRequest,
    ApprovalStatus,
    AutonomyLevel,
    AutonomyPolicy,
)
from app.audit.models import AuditEventType, AuditResult
from app.audit.service import log_audit_event
from app.core.exceptions import NotFoundError


# Time window during which a recently-APPROVED request lets the executor
# skip the approval check on the same (task, action) combo. Keeps the
# task moving forward instead of asking again on every tool_use iteration.
APPROVED_REUSE_WINDOW = timedelta(hours=1)

# Default expiration for PENDING requests. After this, a background worker
# (P0.8) marks them EXPIRED.
DEFAULT_EXPIRY = timedelta(hours=24)


@dataclass
class ApprovalDecision:
    """
    What the executor should do for a given (agent, action) check.

    action_to_take:
    - "execute"        → run the tool normally
    - "shadow_skip"    → DON'T run it, return a fake "{shadow_mode: true}" result
    - "wait_approval"  → pause: mark task WAITING_APPROVAL and exit the loop
    """

    action_to_take: str  # "execute" | "shadow_skip" | "wait_approval"
    autonomy_level: AutonomyLevel
    approval_request_id: uuid.UUID | None  # populated for ALL outcomes
    matched_scope: str  # for diagnostics: "agent:..." / "dept:..." / "global" / "default" / "hardcoded:DELETE"


class ApprovalService:
    """Per-tenant approval logic. All operations are org-scoped."""

    def __init__(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> None:
        self.db = db
        self.org_id = org_id
        self.actor_user_id = actor_user_id

    # ─── Level resolution ───

    async def resolve_level(
        self, agent: Agent, action: str
    ) -> tuple[AutonomyLevel, str]:
        """
        Return (effective_level, matched_scope).

        Precedence:
        1. DELETE:* → MANUAL (hardcoded, no override)
        2. Policy at agent scope (agent:<agent_id>)
        3. Policy at dept scope (dept:<agent.department_id>)
        4. Policy at global scope (global)
        5. Default → MANUAL

        Within a single scope, more specific action patterns beat "*".
        """
        # Rule 1: hardcoded DELETE → MANUAL
        if action.upper().startswith("DELETE:") or action == "DELETE":
            return AutonomyLevel.MANUAL, "hardcoded:DELETE"

        # Build scope precedence list
        scopes_to_check = [f"agent:{agent.id}"]
        if agent.department_id:
            scopes_to_check.append(f"dept:{agent.department_id}")
        scopes_to_check.append("global")

        for scope_key in scopes_to_check:
            level, _matched_pattern = await self._find_matching_policy(scope_key, action)
            if level is not None:
                return level, scope_key

        # Default — no policy found
        return AutonomyLevel.MANUAL, "default"

    async def _find_matching_policy(
        self, scope_key: str, action: str
    ) -> tuple[AutonomyLevel | None, str | None]:
        """
        Within a single scope, find the best-matching policy.
        Most specific wins:
        - exact match ("assign_task")
        - prefix match ("DELETE:*" matches "DELETE:agent")
        - wildcard ("*") last
        """
        result = await self.db.execute(
            select(AutonomyPolicy).where(
                AutonomyPolicy.organization_id == self.org_id,
                AutonomyPolicy.scope_key == scope_key,
            )
        )
        policies = list(result.scalars().all())
        if not policies:
            return None, None

        # Try exact match first
        for p in policies:
            if p.action_pattern == action:
                return p.autonomy_level, p.action_pattern

        # Then prefix patterns (sorted longest first — more specific wins)
        prefix_patterns = sorted(
            [p for p in policies if p.action_pattern.endswith(":*")],
            key=lambda p: -len(p.action_pattern),
        )
        for p in prefix_patterns:
            prefix = p.action_pattern[:-2]  # strip ":*"
            if action.startswith(prefix + ":"):
                return p.autonomy_level, p.action_pattern

        # Then wildcard
        for p in policies:
            if p.action_pattern == "*":
                return p.autonomy_level, p.action_pattern

        return None, None

    # ─── The main entry point used by the executor ───

    async def check_or_request(
        self,
        agent: Agent,
        action: str,
        action_input: dict,
        task_id: uuid.UUID | None = None,
    ) -> ApprovalDecision:
        """
        The executor calls this before every tool execution.

        Logic flow:
        1. If a PENDING request for this (task_id, action) already exists → wait
        2. If an APPROVED request exists in the last APPROVED_REUSE_WINDOW → execute
        3. If a REJECTED request exists → wait (don't loop; the task is dead)
        4. Otherwise, resolve level and act accordingly
        """
        # Idempotency: if there's already a decision for this (task, action) recent
        if task_id is not None:
            existing = await self._find_recent_request(task_id, action)
            if existing is not None:
                if existing.status == ApprovalStatus.PENDING:
                    return ApprovalDecision(
                        action_to_take="wait_approval",
                        autonomy_level=existing.autonomy_level,
                        approval_request_id=existing.id,
                        matched_scope="reused_pending",
                    )
                if existing.status == ApprovalStatus.APPROVED:
                    age = datetime.now(timezone.utc) - (existing.decided_at or existing.requested_at)
                    if age <= APPROVED_REUSE_WINDOW:
                        return ApprovalDecision(
                            action_to_take="execute",
                            autonomy_level=existing.autonomy_level,
                            approval_request_id=existing.id,
                            matched_scope="reused_approved",
                        )
                if existing.status == ApprovalStatus.REJECTED:
                    return ApprovalDecision(
                        action_to_take="wait_approval",  # task ends as REJECTED at the executor level
                        autonomy_level=existing.autonomy_level,
                        approval_request_id=existing.id,
                        matched_scope="reused_rejected",
                    )

        # Fresh resolution
        level, matched_scope = await self.resolve_level(agent, action)

        if level == AutonomyLevel.SHADOW:
            req = await self._record_terminal_request(
                agent, action, action_input, task_id,
                level, ApprovalStatus.SHADOW_LOGGED,
            )
            await log_audit_event(
                self.db, organization_id=self.org_id,
                event_type=AuditEventType.SHADOW_ACTION_LOGGED,
                resource_type="approval_request", resource_id=req.id,
                actor_agent_id=agent.id,
                input_payload=action_input,
                context={"action": action, "task_id": str(task_id) if task_id else None},
            )
            return ApprovalDecision(
                action_to_take="shadow_skip",
                autonomy_level=level,
                approval_request_id=req.id,
                matched_scope=matched_scope,
            )

        if level == AutonomyLevel.AUTO:
            req = await self._record_terminal_request(
                agent, action, action_input, task_id,
                level, ApprovalStatus.AUTO_EXECUTED,
            )
            return ApprovalDecision(
                action_to_take="execute",
                autonomy_level=level,
                approval_request_id=req.id,
                matched_scope=matched_scope,
            )

        if level == AutonomyLevel.COPILOT:
            req = await self._record_terminal_request(
                agent, action, action_input, task_id,
                level, ApprovalStatus.COPILOT_NOTIFIED,
            )
            # Notification creation happens in the executor (after actual execution)
            # to capture the result. We just record the request here.
            return ApprovalDecision(
                action_to_take="execute",
                autonomy_level=level,
                approval_request_id=req.id,
                matched_scope=matched_scope,
            )

        # Level MANUAL: create PENDING and pause
        req = ApprovalRequest(
            organization_id=self.org_id,
            agent_id=agent.id,
            task_id=task_id,
            action=action,
            action_input=action_input,
            autonomy_level=level,
            status=ApprovalStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + DEFAULT_EXPIRY,
        )
        self.db.add(req)
        await self.db.flush()

        await log_audit_event(
            self.db, organization_id=self.org_id,
            event_type=AuditEventType.APPROVAL_REQUESTED,
            resource_type="approval_request", resource_id=req.id,
            actor_agent_id=agent.id,
            input_payload=action_input,
            autonomy_level=int(level),
            context={"action": action, "task_id": str(task_id) if task_id else None,
                     "matched_scope": matched_scope},
        )

        return ApprovalDecision(
            action_to_take="wait_approval",
            autonomy_level=level,
            approval_request_id=req.id,
            matched_scope=matched_scope,
        )

    # ─── Approve / Reject ───

    async def approve(
        self, approval_id: uuid.UUID, user_id: uuid.UUID
    ) -> ApprovalRequest:
        req = await self._require_request(approval_id)
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot approve: status is {req.status.value}")

        req.status = ApprovalStatus.APPROVED
        req.approved_by_user_id = user_id
        req.decided_at = datetime.now(timezone.utc)

        await log_audit_event(
            self.db, organization_id=self.org_id,
            event_type=AuditEventType.APPROVAL_GRANTED,
            resource_type="approval_request", resource_id=req.id,
            actor_user_id=user_id,
            approved_by_user_id=user_id,
            autonomy_level=int(req.autonomy_level),
            context={"action": req.action, "task_id": str(req.task_id) if req.task_id else None},
        )

        await self.db.flush()
        return req

    async def reject(
        self, approval_id: uuid.UUID, user_id: uuid.UUID, reason: str
    ) -> ApprovalRequest:
        req = await self._require_request(approval_id)
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot reject: status is {req.status.value}")

        req.status = ApprovalStatus.REJECTED
        req.approved_by_user_id = user_id  # who decided (rejected)
        req.rejected_reason = reason
        req.decided_at = datetime.now(timezone.utc)

        await log_audit_event(
            self.db, organization_id=self.org_id,
            event_type=AuditEventType.APPROVAL_REJECTED,
            resource_type="approval_request", resource_id=req.id,
            actor_user_id=user_id,
            autonomy_level=int(req.autonomy_level),
            context={"action": req.action, "reason": reason[:200],
                     "task_id": str(req.task_id) if req.task_id else None},
        )

        await self.db.flush()
        return req

    # ─── Queries ───

    async def list_requests(
        self,
        status: ApprovalStatus | None = None,
        agent_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[ApprovalRequest], int]:
        filters = [ApprovalRequest.organization_id == self.org_id]
        if status is not None:
            filters.append(ApprovalRequest.status == status)
        if agent_id is not None:
            filters.append(ApprovalRequest.agent_id == agent_id)
        if task_id is not None:
            filters.append(ApprovalRequest.task_id == task_id)

        where = and_(*filters)

        count_result = await self.db.execute(select(ApprovalRequest).where(where))
        total = len(count_result.scalars().all())

        offset = (page - 1) * size
        stmt = (
            select(ApprovalRequest)
            .where(where)
            .order_by(desc(ApprovalRequest.requested_at))
            .offset(offset)
            .limit(size)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_request(self, approval_id: uuid.UUID) -> ApprovalRequest:
        return await self._require_request(approval_id)

    # ─── Internals ───

    async def _find_recent_request(
        self, task_id: uuid.UUID, action: str
    ) -> ApprovalRequest | None:
        """Look up the most recent request for (task_id, action) — for idempotency."""
        result = await self.db.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.organization_id == self.org_id,
                ApprovalRequest.task_id == task_id,
                ApprovalRequest.action == action,
            )
            .order_by(desc(ApprovalRequest.requested_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _record_terminal_request(
        self,
        agent: Agent,
        action: str,
        action_input: dict,
        task_id: uuid.UUID | None,
        level: AutonomyLevel,
        terminal_status: ApprovalStatus,
    ) -> ApprovalRequest:
        """For Levels 0/1/2 — record a request that's done at creation time."""
        req = ApprovalRequest(
            organization_id=self.org_id,
            agent_id=agent.id,
            task_id=task_id,
            action=action,
            action_input=action_input,
            autonomy_level=level,
            status=terminal_status,
            requested_at=datetime.now(timezone.utc),
            decided_at=datetime.now(timezone.utc),
        )
        self.db.add(req)
        await self.db.flush()
        return req

    async def _require_request(self, approval_id: uuid.UUID) -> ApprovalRequest:
        result = await self.db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.organization_id == self.org_id,
            )
        )
        req = result.scalar_one_or_none()
        if req is None:
            raise NotFoundError(f"Approval request {approval_id} not found")
        return req


# ─────────────────────────────────────────────────────────────────────────────
# PolicyService — separate, for admin endpoints
# ─────────────────────────────────────────────────────────────────────────────


class PolicyService:
    """CRUD for AutonomyPolicy rows + preview tool."""

    def __init__(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> None:
        self.db = db
        self.org_id = org_id
        self.actor_user_id = actor_user_id

    async def list_policies(self) -> list[AutonomyPolicy]:
        result = await self.db.execute(
            select(AutonomyPolicy)
            .where(AutonomyPolicy.organization_id == self.org_id)
            .order_by(AutonomyPolicy.scope_key, AutonomyPolicy.action_pattern)
        )
        return list(result.scalars().all())

    async def create_policy(
        self,
        scope_key: str,
        action_pattern: str,
        autonomy_level: AutonomyLevel,
        auto_promote_threshold: int | None = None,
    ) -> AutonomyPolicy:
        policy = AutonomyPolicy(
            organization_id=self.org_id,
            scope_key=scope_key,
            action_pattern=action_pattern,
            autonomy_level=autonomy_level,
            auto_promote_threshold=auto_promote_threshold,
            created_by_user_id=self.actor_user_id,
        )
        self.db.add(policy)
        await self.db.flush()

        await log_audit_event(
            self.db, organization_id=self.org_id,
            event_type=AuditEventType.AUTONOMY_POLICY_CHANGED,
            resource_type="autonomy_policy", resource_id=policy.id,
            actor_user_id=self.actor_user_id,
            context={
                "change": "create",
                "scope_key": scope_key,
                "action_pattern": action_pattern,
                "autonomy_level": int(autonomy_level),
            },
        )
        return policy

    async def update_policy(
        self,
        policy_id: uuid.UUID,
        autonomy_level: AutonomyLevel | None,
        auto_promote_threshold: int | None,
    ) -> AutonomyPolicy:
        policy = await self._require_policy(policy_id)
        changes = {}
        if autonomy_level is not None and autonomy_level != policy.autonomy_level:
            changes["autonomy_level"] = {"from": int(policy.autonomy_level), "to": int(autonomy_level)}
            policy.autonomy_level = autonomy_level
        if auto_promote_threshold != policy.auto_promote_threshold:
            changes["auto_promote_threshold"] = {
                "from": policy.auto_promote_threshold, "to": auto_promote_threshold,
            }
            policy.auto_promote_threshold = auto_promote_threshold

        await self.db.flush()

        if changes:
            await log_audit_event(
                self.db, organization_id=self.org_id,
                event_type=AuditEventType.AUTONOMY_POLICY_CHANGED,
                resource_type="autonomy_policy", resource_id=policy.id,
                actor_user_id=self.actor_user_id,
                context={"change": "update", "changes": changes,
                         "scope_key": policy.scope_key,
                         "action_pattern": policy.action_pattern},
            )
        return policy

    async def delete_policy(self, policy_id: uuid.UUID) -> None:
        policy = await self._require_policy(policy_id)
        await log_audit_event(
            self.db, organization_id=self.org_id,
            event_type=AuditEventType.AUTONOMY_POLICY_CHANGED,
            resource_type="autonomy_policy", resource_id=policy.id,
            actor_user_id=self.actor_user_id,
            context={"change": "delete",
                     "scope_key": policy.scope_key,
                     "action_pattern": policy.action_pattern,
                     "previous_level": int(policy.autonomy_level)},
        )
        await self.db.delete(policy)
        await self.db.flush()

    async def preview_level(
        self, agent_id: uuid.UUID, action: str
    ) -> tuple[AutonomyLevel, AutonomyPolicy | None, str | None, str | None]:
        """For 'what would happen' UI tooling."""
        from app.agents.models import Agent

        result = await self.db.execute(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.organization_id == self.org_id,
            )
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise NotFoundError(f"Agent {agent_id} not found")

        approval_service = ApprovalService(self.db, self.org_id)
        level, matched_scope = await approval_service.resolve_level(agent, action)

        # Find the actual policy that matched (if any)
        matched_policy: AutonomyPolicy | None = None
        matched_pattern: str | None = None
        if matched_scope not in ("hardcoded:DELETE", "default"):
            _, matched_pattern = await approval_service._find_matching_policy(matched_scope, action)
            if matched_pattern is not None:
                policy_result = await self.db.execute(
                    select(AutonomyPolicy).where(
                        AutonomyPolicy.organization_id == self.org_id,
                        AutonomyPolicy.scope_key == matched_scope,
                        AutonomyPolicy.action_pattern == matched_pattern,
                    )
                )
                matched_policy = policy_result.scalar_one_or_none()

        return level, matched_policy, matched_scope, matched_pattern

    async def _require_policy(self, policy_id: uuid.UUID) -> AutonomyPolicy:
        result = await self.db.execute(
            select(AutonomyPolicy).where(
                AutonomyPolicy.id == policy_id,
                AutonomyPolicy.organization_id == self.org_id,
            )
        )
        policy = result.scalar_one_or_none()
        if policy is None:
            raise NotFoundError(f"Policy {policy_id} not found")
        return policy


# ─── Background expiration (P0.8) ─────────────────────────────────────────────
# Module-level (not on the service) so the worker can call it without an org
# context — it sweeps across ALL tenants in one pass, auditing each request under
# its own organization_id. Takes a session so it's unit-testable with the test DB;
# the worker (app/workers/approval_expirer.py) owns opening + committing it.
async def expire_overdue_approvals(db: AsyncSession) -> int:
    """Mark PENDING approval requests past their expires_at as EXPIRED. Returns count."""
    now = datetime.now(timezone.utc)
    overdue = (
        await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status == ApprovalStatus.PENDING,
                ApprovalRequest.expires_at.is_not(None),
                ApprovalRequest.expires_at < now,
            )
        )
    ).scalars().all()

    for req in overdue:
        req.status = ApprovalStatus.EXPIRED
        req.decided_at = now
        await log_audit_event(
            db,
            organization_id=req.organization_id,
            event_type=AuditEventType.APPROVAL_EXPIRED,
            resource_type="approval_request",
            resource_id=req.id,
            actor_agent_id=req.agent_id,
            result=AuditResult.FAILURE,  # the action did NOT get approved in time
            context={"action": req.action, "expired_at": now.isoformat()},
        )

    return len(overdue)
