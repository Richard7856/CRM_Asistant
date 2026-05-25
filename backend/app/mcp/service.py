"""
ScopeService — manages what agents/tools a department is allowed to invoke.

Key design:
- All scope checks query the DB fresh — no in-memory cache. This guarantees
  that revoking a permission has effect within milliseconds (promise of
  the landing v2: "permisos revocables al instante").
- Cross-org grants are rejected: a department in Org A cannot be granted
  an agent that belongs to Org B (enforced by validating organization_id
  on both sides before insert).
- Every grant/revoke generates an audit_log entry (AuditEventType.MCP_*).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.audit.models import AuditEventType
from app.audit.service import log_audit_event
from app.auth.models import User, UserRole
from app.core.exceptions import NotFoundError
from app.departments.models import Department
from app.mcp.models import DepartmentAgentPermission, DepartmentToolPermission


@dataclass
class UserScope:
    """
    The set of agents and tools a user is allowed to invoke through the Router.

    - For OWNER/ADMIN: `is_org_wide=True` and lists are empty — they have full access.
    - For MEMBER/VIEWER: lists contain ONLY the resources granted to their department.
    """

    user_id: uuid.UUID
    organization_id: uuid.UUID
    department_id: uuid.UUID | None
    is_org_wide: bool
    agent_ids: set[uuid.UUID]
    tool_names: set[str]

    def can_invoke_agent(self, agent_id: uuid.UUID) -> bool:
        return self.is_org_wide or agent_id in self.agent_ids

    def can_invoke_tool(self, tool_name: str) -> bool:
        return self.is_org_wide or tool_name in self.tool_names


class ScopeService:
    """Per-tenant scope management. All operations are org-scoped."""

    def __init__(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> None:
        self.db = db
        self.org_id = org_id
        self.actor_user_id = actor_user_id

    # ─── User scope resolution (the hot path — called by /mcp/route) ───

    async def resolve_scope_for_user(self, user: User) -> UserScope:
        """
        Resolve the effective scope for a user.

        For OWNER/ADMIN: returns is_org_wide=True (no DB queries needed).
        For MEMBER/VIEWER: loads their department's grants from DB.
        Always queries fresh — no caching, so revokes take effect immediately.
        """
        if user.role in (UserRole.OWNER, UserRole.ADMIN):
            return UserScope(
                user_id=user.id,
                organization_id=user.organization_id,
                department_id=user.department_id,
                is_org_wide=True,
                agent_ids=set(),
                tool_names=set(),
            )

        # MEMBER/VIEWER must have a department assigned
        if user.department_id is None:
            return UserScope(
                user_id=user.id,
                organization_id=user.organization_id,
                department_id=None,
                is_org_wide=False,
                agent_ids=set(),
                tool_names=set(),
            )

        agent_ids = await self._load_agent_scope(user.department_id)
        tool_names = await self._load_tool_scope(user.department_id)

        return UserScope(
            user_id=user.id,
            organization_id=user.organization_id,
            department_id=user.department_id,
            is_org_wide=False,
            agent_ids=agent_ids,
            tool_names=tool_names,
        )

    async def _load_agent_scope(self, department_id: uuid.UUID) -> set[uuid.UUID]:
        result = await self.db.execute(
            select(DepartmentAgentPermission.agent_id).where(
                DepartmentAgentPermission.department_id == department_id
            )
        )
        return set(result.scalars().all())

    async def _load_tool_scope(self, department_id: uuid.UUID) -> set[str]:
        result = await self.db.execute(
            select(DepartmentToolPermission.tool_name).where(
                DepartmentToolPermission.department_id == department_id
            )
        )
        return set(result.scalars().all())

    # ─── Scope inspection (for admin endpoints) ───

    async def get_department_scope(
        self, department_id: uuid.UUID
    ) -> tuple[Department, list[Agent], list[str]]:
        """Returns (department, allowed_agents, allowed_tool_names)."""
        dept = await self._require_department(department_id)

        agent_result = await self.db.execute(
            select(Agent).join(
                DepartmentAgentPermission,
                DepartmentAgentPermission.agent_id == Agent.id,
            ).where(
                DepartmentAgentPermission.department_id == department_id
            )
        )
        agents = list(agent_result.scalars().all())

        tool_result = await self.db.execute(
            select(DepartmentToolPermission.tool_name).where(
                DepartmentToolPermission.department_id == department_id
            )
        )
        tool_names = list(tool_result.scalars().all())

        return dept, agents, tool_names

    # ─── Grant / Revoke ───

    async def grant_agent(
        self, department_id: uuid.UUID, agent_id: uuid.UUID
    ) -> None:
        """Allow a department to invoke a specific agent. Idempotent."""
        dept = await self._require_department(department_id)
        agent = await self._require_agent(agent_id)

        # Cross-org guard — critical
        if dept.organization_id != agent.organization_id:
            raise ValueError(
                "Cross-org grant blocked: department and agent belong to different organizations"
            )

        # ON CONFLICT DO NOTHING — same (dept, agent) twice is a no-op
        stmt = (
            pg_insert(DepartmentAgentPermission)
            .values(
                department_id=department_id,
                agent_id=agent_id,
                granted_by_user_id=self.actor_user_id,
            )
            .on_conflict_do_nothing(
                index_elements=["department_id", "agent_id"]
            )
        )
        await self.db.execute(stmt)

        await log_audit_event(
            self.db, organization_id=self.org_id,
            event_type=AuditEventType.MCP_PERMISSION_GRANTED,
            resource_type="department_scope", resource_id=department_id,
            actor_user_id=self.actor_user_id,
            context={
                "scope_type": "agent",
                "agent_id": str(agent_id),
                "agent_name": agent.name,
                "department_id": str(department_id),
                "department_name": dept.name,
            },
        )

    async def revoke_agent(
        self, department_id: uuid.UUID, agent_id: uuid.UUID
    ) -> None:
        """Remove an agent from a department's scope. Idempotent."""
        dept = await self._require_department(department_id)
        agent_result = await self.db.execute(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.organization_id == self.org_id,
            )
        )
        agent = agent_result.scalar_one_or_none()
        if agent is None:
            raise NotFoundError(f"Agent {agent_id} not found")

        await self.db.execute(
            delete(DepartmentAgentPermission).where(
                and_(
                    DepartmentAgentPermission.department_id == department_id,
                    DepartmentAgentPermission.agent_id == agent_id,
                )
            )
        )

        await log_audit_event(
            self.db, organization_id=self.org_id,
            event_type=AuditEventType.MCP_PERMISSION_REVOKED,
            resource_type="department_scope", resource_id=department_id,
            actor_user_id=self.actor_user_id,
            context={
                "scope_type": "agent",
                "agent_id": str(agent_id),
                "agent_name": agent.name,
                "department_id": str(department_id),
                "department_name": dept.name,
            },
        )

    async def grant_tool(
        self, department_id: uuid.UUID, tool_name: str
    ) -> None:
        """Allow a department to invoke a specific tool by name. Idempotent."""
        dept = await self._require_department(department_id)

        stmt = (
            pg_insert(DepartmentToolPermission)
            .values(
                department_id=department_id,
                tool_name=tool_name,
                granted_by_user_id=self.actor_user_id,
            )
            .on_conflict_do_nothing(
                index_elements=["department_id", "tool_name"]
            )
        )
        await self.db.execute(stmt)

        await log_audit_event(
            self.db, organization_id=self.org_id,
            event_type=AuditEventType.MCP_PERMISSION_GRANTED,
            resource_type="department_scope", resource_id=department_id,
            actor_user_id=self.actor_user_id,
            context={
                "scope_type": "tool",
                "tool_name": tool_name,
                "department_id": str(department_id),
                "department_name": dept.name,
            },
        )

    async def revoke_tool(
        self, department_id: uuid.UUID, tool_name: str
    ) -> None:
        """Remove a tool from a department's scope. Idempotent."""
        dept = await self._require_department(department_id)

        await self.db.execute(
            delete(DepartmentToolPermission).where(
                and_(
                    DepartmentToolPermission.department_id == department_id,
                    DepartmentToolPermission.tool_name == tool_name,
                )
            )
        )

        await log_audit_event(
            self.db, organization_id=self.org_id,
            event_type=AuditEventType.MCP_PERMISSION_REVOKED,
            resource_type="department_scope", resource_id=department_id,
            actor_user_id=self.actor_user_id,
            context={
                "scope_type": "tool",
                "tool_name": tool_name,
                "department_id": str(department_id),
                "department_name": dept.name,
            },
        )

    async def replace_department_scope(
        self,
        department_id: uuid.UUID,
        agent_ids: list[uuid.UUID],
        tool_names: list[str],
    ) -> None:
        """
        Replace the entire scope of a department in one operation.

        Useful for the admin UI's "save all changes" flow: delete everything,
        re-insert the new set. Audit logs the bulk operation (with diff context).
        """
        dept = await self._require_department(department_id)

        # Validate every agent belongs to the same org as the department
        if agent_ids:
            agent_check = await self.db.execute(
                select(Agent.id).where(
                    Agent.id.in_(agent_ids),
                    Agent.organization_id == self.org_id,
                )
            )
            valid_agent_ids = set(agent_check.scalars().all())
            invalid = set(agent_ids) - valid_agent_ids
            if invalid:
                raise ValueError(
                    f"Cannot grant agents from another org or non-existent: {invalid}"
                )

        # Wipe + recreate (transactional)
        await self.db.execute(
            delete(DepartmentAgentPermission).where(
                DepartmentAgentPermission.department_id == department_id
            )
        )
        await self.db.execute(
            delete(DepartmentToolPermission).where(
                DepartmentToolPermission.department_id == department_id
            )
        )

        for aid in agent_ids:
            self.db.add(DepartmentAgentPermission(
                department_id=department_id,
                agent_id=aid,
                granted_by_user_id=self.actor_user_id,
            ))
        for tname in tool_names:
            self.db.add(DepartmentToolPermission(
                department_id=department_id,
                tool_name=tname,
                granted_by_user_id=self.actor_user_id,
            ))

        await self.db.flush()

        # Audit as a single "bulk scope replaced" event
        await log_audit_event(
            self.db, organization_id=self.org_id,
            event_type=AuditEventType.MCP_PERMISSION_GRANTED,
            resource_type="department_scope", resource_id=department_id,
            actor_user_id=self.actor_user_id,
            context={
                "scope_type": "bulk_replace",
                "department_id": str(department_id),
                "department_name": dept.name,
                "agent_count": len(agent_ids),
                "tool_count": len(tool_names),
                "agent_ids": [str(a) for a in agent_ids],
                "tool_names": list(tool_names),
            },
        )

    # ─── Internals ───

    async def _require_department(self, department_id: uuid.UUID) -> Department:
        result = await self.db.execute(
            select(Department).where(
                Department.id == department_id,
                Department.organization_id == self.org_id,
            )
        )
        dept = result.scalar_one_or_none()
        if dept is None:
            raise NotFoundError(f"Department {department_id} not found")
        return dept

    async def _require_agent(self, agent_id: uuid.UUID) -> Agent:
        result = await self.db.execute(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.organization_id == self.org_id,
            )
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise NotFoundError(f"Agent {agent_id} not found")
        return agent
