"""
Approval system tests — P0.5.

Three layers covered:
1. ApprovalService.resolve_level — the precedence chain
2. ApprovalService.check_or_request — what the executor consumes
3. Endpoints (queue + admin) — what humans see

Plus integration tests with the executor (via _execute_agent_tool) to
verify Levels 0/1/3 actually do what they're supposed to do at the
end of the tool_use loop.
"""

import uuid

import pytest
from sqlalchemy import select

from app.agents.models import Agent, AgentOrigin, AgentStatus
from app.approvals.models import (
    ApprovalRequest,
    ApprovalStatus,
    AutonomyLevel,
    AutonomyPolicy,
)
from app.approvals.service import ApprovalService, PolicyService
from app.audit.models import AuditEventType, AuditLog
from app.auth.models import User, UserRole
from app.auth.service import create_access_token, hash_password
from app.departments.models import Department
from app.tasks.models import Task, TaskStatus


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _make_department(db, org_id, name="Sales"):
    suffix = uuid.uuid4().hex[:8]
    dept = Department(name=f"{name}-{suffix}", slug=f"{name.lower()}-{suffix}", organization_id=org_id)
    db.add(dept)
    await db.flush()
    return dept


async def _make_agent(db, org_id, dept_id=None, name="Worker"):
    suffix = uuid.uuid4().hex[:8]
    agent = Agent(
        name=f"{name}-{suffix}",
        slug=f"{name.lower()}-{suffix}",
        origin=AgentOrigin.INTERNAL,
        status=AgentStatus.ACTIVE,
        organization_id=org_id,
        department_id=dept_id,
    )
    db.add(agent)
    await db.flush()
    return agent


async def _make_task(db, org_id, agent_id, title="Test Task"):
    task = Task(
        title=title,
        organization_id=org_id,
        assigned_to=agent_id,
        status=TaskStatus.IN_PROGRESS,
    )
    db.add(task)
    await db.flush()
    return task


# ─────────────────────────────────────────────────────────────────────────────
# TestResolveLevel — precedence chain + DELETE hardcoded rule
# ─────────────────────────────────────────────────────────────────────────────


class TestResolveLevel:
    async def test_default_is_manual_when_no_policy(self, db, test_org):
        """If no policy matches → Level 3 MANUAL (the safe default)."""
        agent = await _make_agent(db, test_org.id)
        service = ApprovalService(db, test_org.id)

        level, scope = await service.resolve_level(agent, "any_action")
        assert level == AutonomyLevel.MANUAL
        assert scope == "default"

    async def test_delete_action_is_always_manual_even_with_auto_policy(
        self, db, test_org
    ):
        """DELETE:* must NEVER be overridable — even a wildcard AUTO policy can't lower it."""
        agent = await _make_agent(db, test_org.id)

        # Create a permissive global policy: anything → AUTO
        db.add(AutonomyPolicy(
            organization_id=test_org.id,
            scope_key="global",
            action_pattern="*",
            autonomy_level=AutonomyLevel.AUTO,
        ))
        await db.flush()

        service = ApprovalService(db, test_org.id)
        # Even with the AUTO wildcard, DELETE must remain MANUAL
        level, scope = await service.resolve_level(agent, "DELETE:agent")
        assert level == AutonomyLevel.MANUAL
        assert scope == "hardcoded:DELETE"

        # And a non-DELETE action falls through to the wildcard
        level2, scope2 = await service.resolve_level(agent, "create_agent")
        assert level2 == AutonomyLevel.AUTO

    async def test_agent_policy_beats_dept_policy_beats_global(self, db, test_org):
        """Precedence: agent > dept > global."""
        dept = await _make_department(db, test_org.id)
        agent = await _make_agent(db, test_org.id, dept.id)

        # Set conflicting levels at each scope
        db.add(AutonomyPolicy(
            organization_id=test_org.id, scope_key="global",
            action_pattern="*", autonomy_level=AutonomyLevel.MANUAL,
        ))
        db.add(AutonomyPolicy(
            organization_id=test_org.id, scope_key=f"dept:{dept.id}",
            action_pattern="*", autonomy_level=AutonomyLevel.COPILOT,
        ))
        db.add(AutonomyPolicy(
            organization_id=test_org.id, scope_key=f"agent:{agent.id}",
            action_pattern="*", autonomy_level=AutonomyLevel.AUTO,
        ))
        await db.flush()

        service = ApprovalService(db, test_org.id)
        level, scope = await service.resolve_level(agent, "create_agent")
        assert level == AutonomyLevel.AUTO  # agent policy wins
        assert scope == f"agent:{agent.id}"

    async def test_exact_action_pattern_beats_wildcard(self, db, test_org):
        """Within a scope, exact match beats wildcard."""
        agent = await _make_agent(db, test_org.id)
        db.add(AutonomyPolicy(
            organization_id=test_org.id, scope_key="global",
            action_pattern="*", autonomy_level=AutonomyLevel.MANUAL,
        ))
        db.add(AutonomyPolicy(
            organization_id=test_org.id, scope_key="global",
            action_pattern="assign_task", autonomy_level=AutonomyLevel.AUTO,
        ))
        await db.flush()

        service = ApprovalService(db, test_org.id)
        # assign_task → exact match → AUTO
        level1, _ = await service.resolve_level(agent, "assign_task")
        assert level1 == AutonomyLevel.AUTO
        # Other actions → wildcard → MANUAL
        level2, _ = await service.resolve_level(agent, "create_agent")
        assert level2 == AutonomyLevel.MANUAL


# ─────────────────────────────────────────────────────────────────────────────
# TestCheckOrRequest — what the executor consumes
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckOrRequest:
    async def test_level_shadow_returns_shadow_skip(self, db, test_org):
        agent = await _make_agent(db, test_org.id)
        db.add(AutonomyPolicy(
            organization_id=test_org.id, scope_key="global",
            action_pattern="*", autonomy_level=AutonomyLevel.SHADOW,
        ))
        await db.flush()

        service = ApprovalService(db, test_org.id)
        decision = await service.check_or_request(
            agent, "some_action", {"key": "value"}, task_id=None,
        )
        assert decision.action_to_take == "shadow_skip"
        assert decision.autonomy_level == AutonomyLevel.SHADOW

        # Check the request was recorded as SHADOW_LOGGED
        req_result = await db.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == decision.approval_request_id)
        )
        req = req_result.scalar_one()
        assert req.status == ApprovalStatus.SHADOW_LOGGED

    async def test_level_auto_returns_execute(self, db, test_org):
        agent = await _make_agent(db, test_org.id)
        db.add(AutonomyPolicy(
            organization_id=test_org.id, scope_key="global",
            action_pattern="*", autonomy_level=AutonomyLevel.AUTO,
        ))
        await db.flush()

        service = ApprovalService(db, test_org.id)
        decision = await service.check_or_request(agent, "some_action", {}, None)
        assert decision.action_to_take == "execute"
        assert decision.autonomy_level == AutonomyLevel.AUTO

        req = await db.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == decision.approval_request_id)
        )
        assert req.scalar_one().status == ApprovalStatus.AUTO_EXECUTED

    async def test_level_manual_returns_wait_approval(self, db, test_org):
        """No policy = default MANUAL = wait_approval + create PENDING request."""
        agent = await _make_agent(db, test_org.id)
        service = ApprovalService(db, test_org.id)

        decision = await service.check_or_request(agent, "critical_action", {"target": "X"}, None)
        assert decision.action_to_take == "wait_approval"
        assert decision.autonomy_level == AutonomyLevel.MANUAL

        req = await db.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == decision.approval_request_id)
        )
        r = req.scalar_one()
        assert r.status == ApprovalStatus.PENDING
        assert r.action == "critical_action"
        assert r.action_input == {"target": "X"}
        assert r.expires_at is not None

    async def test_recent_approved_lets_executor_run(self, db, test_org):
        """If there's an APPROVED request for the same (task, action) → execute (idempotency)."""
        from datetime import datetime, timezone
        agent = await _make_agent(db, test_org.id)
        task = await _make_task(db, test_org.id, agent.id)

        # Pre-existing APPROVED request (just now)
        approved_req = ApprovalRequest(
            organization_id=test_org.id,
            agent_id=agent.id,
            task_id=task.id,
            action="dangerous_action",
            action_input={"x": 1},
            autonomy_level=AutonomyLevel.MANUAL,
            status=ApprovalStatus.APPROVED,
            decided_at=datetime.now(timezone.utc),
        )
        db.add(approved_req)
        await db.flush()

        service = ApprovalService(db, test_org.id)
        decision = await service.check_or_request(agent, "dangerous_action", {"x": 1}, task.id)
        assert decision.action_to_take == "execute"
        assert decision.matched_scope == "reused_approved"

    async def test_existing_pending_returns_wait(self, db, test_org):
        """If a PENDING request already exists, return wait (don't create duplicate)."""
        agent = await _make_agent(db, test_org.id)
        task = await _make_task(db, test_org.id, agent.id)

        existing = ApprovalRequest(
            organization_id=test_org.id, agent_id=agent.id, task_id=task.id,
            action="x", action_input={}, autonomy_level=AutonomyLevel.MANUAL,
            status=ApprovalStatus.PENDING,
        )
        db.add(existing)
        await db.flush()

        service = ApprovalService(db, test_org.id)
        decision = await service.check_or_request(agent, "x", {}, task.id)
        assert decision.action_to_take == "wait_approval"
        assert decision.approval_request_id == existing.id
        assert decision.matched_scope == "reused_pending"

    async def test_existing_rejected_returns_wait_not_execute(self, db, test_org):
        """If a prior request was REJECTED for this (task, action), don't loop forever."""
        agent = await _make_agent(db, test_org.id)
        task = await _make_task(db, test_org.id, agent.id)

        rejected = ApprovalRequest(
            organization_id=test_org.id, agent_id=agent.id, task_id=task.id,
            action="x", action_input={}, autonomy_level=AutonomyLevel.MANUAL,
            status=ApprovalStatus.REJECTED,
            rejected_reason="No.",
        )
        db.add(rejected)
        await db.flush()

        service = ApprovalService(db, test_org.id)
        decision = await service.check_or_request(agent, "x", {}, task.id)
        assert decision.action_to_take == "wait_approval"
        assert decision.matched_scope == "reused_rejected"


# ─────────────────────────────────────────────────────────────────────────────
# TestApproveReject
# ─────────────────────────────────────────────────────────────────────────────


class TestApproveReject:
    async def test_approve_changes_status_and_records_user(self, db, test_org, test_user):
        agent = await _make_agent(db, test_org.id)
        service = ApprovalService(db, test_org.id)
        decision = await service.check_or_request(agent, "x", {}, None)
        assert decision.action_to_take == "wait_approval"

        approved = await service.approve(decision.approval_request_id, test_user.id)
        assert approved.status == ApprovalStatus.APPROVED
        assert approved.approved_by_user_id == test_user.id
        assert approved.decided_at is not None

    async def test_approve_twice_raises_value_error(self, db, test_org, test_user):
        agent = await _make_agent(db, test_org.id)
        service = ApprovalService(db, test_org.id)
        decision = await service.check_or_request(agent, "x", {}, None)
        await service.approve(decision.approval_request_id, test_user.id)

        with pytest.raises(ValueError):
            await service.approve(decision.approval_request_id, test_user.id)

    async def test_reject_records_reason(self, db, test_org, test_user):
        agent = await _make_agent(db, test_org.id)
        service = ApprovalService(db, test_org.id)
        decision = await service.check_or_request(agent, "x", {}, None)

        rejected = await service.reject(decision.approval_request_id, test_user.id, "Too risky.")
        assert rejected.status == ApprovalStatus.REJECTED
        assert rejected.rejected_reason == "Too risky."
        assert rejected.approved_by_user_id == test_user.id  # who decided


# ─────────────────────────────────────────────────────────────────────────────
# TestEndpoints — the human-facing queue + admin policy CRUD
# ─────────────────────────────────────────────────────────────────────────────


class TestEndpoints:
    async def test_list_approvals_filters_by_status(
        self, client, db, test_org, auth_headers
    ):
        agent = await _make_agent(db, test_org.id)
        service = ApprovalService(db, test_org.id)
        # Create 1 PENDING (default MANUAL) + 1 SHADOW_LOGGED
        await service.check_or_request(agent, "act1", {}, None)
        db.add(AutonomyPolicy(
            organization_id=test_org.id, scope_key=f"agent:{agent.id}",
            action_pattern="*", autonomy_level=AutonomyLevel.SHADOW,
        ))
        await db.flush()
        await service.check_or_request(agent, "act2", {}, None)

        response = await client.get(
            "/api/v1/approvals/?status=pending",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        # All returned items must be pending
        for item in body["items"]:
            assert item["status"] == "pending"

    async def test_approve_endpoint(self, client, db, test_org, auth_headers):
        agent = await _make_agent(db, test_org.id)
        service = ApprovalService(db, test_org.id)
        decision = await service.check_or_request(agent, "x", {}, None)
        await db.flush()

        response = await client.post(
            f"/api/v1/approvals/{decision.approval_request_id}/approve",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

    async def test_reject_endpoint(self, client, db, test_org, auth_headers):
        agent = await _make_agent(db, test_org.id)
        service = ApprovalService(db, test_org.id)
        decision = await service.check_or_request(agent, "x", {}, None)
        await db.flush()

        response = await client.post(
            f"/api/v1/approvals/{decision.approval_request_id}/reject",
            headers=auth_headers,
            json={"reason": "Out of scope for this dept"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"
        assert response.json()["rejected_reason"] == "Out of scope for this dept"

    async def test_member_cannot_access_approval_queue(self, client, db, test_org):
        member = User(
            email=f"m-{uuid.uuid4().hex[:8]}@t.io",
            password_hash=hash_password("Test1234"),
            full_name="M",
            role=UserRole.MEMBER,
            organization_id=test_org.id,
        )
        db.add(member)
        await db.flush()
        token, _ = create_access_token(member.id, test_org.id, member.role.value)

        response = await client.get(
            "/api/v1/approvals/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    async def test_admin_create_policy(self, client, db, test_org, auth_headers):
        response = await client.post(
            "/api/v1/admin/autonomy-policies",
            headers=auth_headers,
            json={
                "scope_key": "global",
                "action_pattern": "*",
                "autonomy_level": 1,  # AUTO
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["autonomy_level"] == 1
        assert body["scope_key"] == "global"

    async def test_admin_preview_policy(self, client, db, test_org, auth_headers):
        agent = await _make_agent(db, test_org.id)
        # Create a global AUTO policy
        db.add(AutonomyPolicy(
            organization_id=test_org.id, scope_key="global",
            action_pattern="*", autonomy_level=AutonomyLevel.AUTO,
        ))
        await db.flush()

        response = await client.post(
            "/api/v1/admin/autonomy-policies/preview",
            headers=auth_headers,
            json={"agent_id": str(agent.id), "action": "anything"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["resolved_level"] == 1  # AUTO
        assert body["matched_scope_key"] == "global"

        # DELETE preview must always come back as MANUAL (hardcoded)
        delete_response = await client.post(
            "/api/v1/admin/autonomy-policies/preview",
            headers=auth_headers,
            json={"agent_id": str(agent.id), "action": "DELETE:agent"},
        )
        assert delete_response.json()["resolved_level"] == 3  # MANUAL
        assert delete_response.json()["matched_scope_key"] == "hardcoded:DELETE"

    async def test_member_cannot_create_policy(self, client, db, test_org):
        member = User(
            email=f"m2-{uuid.uuid4().hex[:8]}@t.io",
            password_hash=hash_password("Test1234"),
            full_name="M2", role=UserRole.MEMBER,
            organization_id=test_org.id,
        )
        db.add(member)
        await db.flush()
        token, _ = create_access_token(member.id, test_org.id, member.role.value)

        response = await client.post(
            "/api/v1/admin/autonomy-policies",
            headers={"Authorization": f"Bearer {token}"},
            json={"scope_key": "global", "action_pattern": "*", "autonomy_level": 1},
        )
        assert response.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# TestAuditEvents — every action generates an audit_log entry
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditEvents:
    async def test_shadow_logged_creates_shadow_audit(self, db, test_org):
        agent = await _make_agent(db, test_org.id)
        db.add(AutonomyPolicy(
            organization_id=test_org.id, scope_key="global",
            action_pattern="*", autonomy_level=AutonomyLevel.SHADOW,
        ))
        await db.flush()

        service = ApprovalService(db, test_org.id)
        await service.check_or_request(agent, "ghost_action", {"x": 1}, None)

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.SHADOW_ACTION_LOGGED,
            )
        )
        assert len(result.scalars().all()) == 1

    async def test_pending_creates_approval_requested_audit(self, db, test_org):
        agent = await _make_agent(db, test_org.id)
        service = ApprovalService(db, test_org.id)
        await service.check_or_request(agent, "dangerous", {}, None)

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.APPROVAL_REQUESTED,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        assert entries[0].autonomy_level == int(AutonomyLevel.MANUAL)

    async def test_approve_creates_approval_granted_audit(
        self, db, test_org, test_user
    ):
        agent = await _make_agent(db, test_org.id)
        service = ApprovalService(db, test_org.id)
        decision = await service.check_or_request(agent, "x", {}, None)
        await service.approve(decision.approval_request_id, test_user.id)

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.APPROVAL_GRANTED,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        assert entries[0].approved_by_user_id == test_user.id

    async def test_policy_create_audits_policy_change(
        self, db, test_org, test_user
    ):
        service = PolicyService(db, test_org.id, actor_user_id=test_user.id)
        await service.create_policy(
            scope_key="global", action_pattern="*", autonomy_level=AutonomyLevel.AUTO,
        )

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.AUTONOMY_POLICY_CHANGED,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        assert entries[0].context["change"] == "create"


# ─────────────────────────────────────────────────────────────────────────────
# TestTenantIsolation
# ─────────────────────────────────────────────────────────────────────────────


class TestTenantIsolation:
    async def test_org_a_policy_does_not_affect_org_b_agent(
        self, db, test_org, second_org
    ):
        """Even if Org A has a wildcard AUTO policy, Org B's agent should still default to MANUAL."""
        agent_b = await _make_agent(db, second_org.id)
        # AUTO policy in Org A
        db.add(AutonomyPolicy(
            organization_id=test_org.id, scope_key="global",
            action_pattern="*", autonomy_level=AutonomyLevel.AUTO,
        ))
        await db.flush()

        # Resolve as Org B service — must NOT see Org A's policy
        service_b = ApprovalService(db, second_org.id)
        level, scope = await service_b.resolve_level(agent_b, "x")
        assert level == AutonomyLevel.MANUAL
        assert scope == "default"

    async def test_approve_request_from_other_org_returns_not_found(
        self, db, test_org, second_org, test_user
    ):
        agent_b = await _make_agent(db, second_org.id)
        service_b = ApprovalService(db, second_org.id)
        decision = await service_b.check_or_request(agent_b, "x", {}, None)
        await db.flush()

        # As Org A admin, try to approve Org B's request → NotFoundError
        service_a = ApprovalService(db, test_org.id, actor_user_id=test_user.id)
        from app.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await service_a.approve(decision.approval_request_id, test_user.id)
