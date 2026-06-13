"""
ScopeService tests — P0.3.1 foundation.

Covers the scope resolution + grant/revoke logic that the MCP Router will use.
The endpoint tests (POST /mcp/route) live in test_mcp_router.py (P0.3.2/.3).
"""

import uuid

import pytest
from sqlalchemy import select

from app.audit.models import AuditEventType, AuditLog
from app.auth.models import User, UserRole
from app.auth.service import hash_password
from app.departments.models import Department
from app.mcp.models import DepartmentAgentPermission, DepartmentToolPermission
from app.mcp.service import ScopeService
from app.agents.models import Agent, AgentOrigin, AgentStatus


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _make_department(db, org_id, name="Marketing"):
    suffix = uuid.uuid4().hex[:8]
    dept = Department(
        name=f"{name}-{suffix}",
        slug=f"{name.lower()}-{suffix}",
        organization_id=org_id,
    )
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


async def _make_member_user(db, org_id, dept_id=None):
    user = User(
        email=f"member-{uuid.uuid4().hex[:8]}@test.io",
        password_hash=hash_password("Test1234"),
        full_name="Test Member",
        role=UserRole.MEMBER,
        organization_id=org_id,
        department_id=dept_id,
    )
    db.add(user)
    await db.flush()
    return user


# ─────────────────────────────────────────────────────────────────────────────
# TestUserScopeResolution — the hot path of the Router
# ─────────────────────────────────────────────────────────────────────────────


class TestUserScopeResolution:
    async def test_owner_gets_org_wide_scope(self, db, test_org, test_user):
        """test_user is OWNER — should get is_org_wide=True without DB queries."""
        # test_user comes from conftest as OWNER
        service = ScopeService(db, test_org.id)
        scope = await service.resolve_scope_for_user(test_user)

        assert scope.is_org_wide is True
        assert scope.user_id == test_user.id
        assert scope.organization_id == test_org.id
        # Owners can invoke anything by definition
        random_agent_id = uuid.uuid4()
        assert scope.can_invoke_agent(random_agent_id) is True
        assert scope.can_invoke_tool("any_tool") is True

    async def test_member_without_department_gets_empty_scope(self, db, test_org):
        """MEMBER without department_id assigned → empty scope, cannot invoke anything."""
        member = await _make_member_user(db, test_org.id, dept_id=None)
        service = ScopeService(db, test_org.id)
        scope = await service.resolve_scope_for_user(member)

        assert scope.is_org_wide is False
        assert scope.department_id is None
        assert scope.agent_ids == set()
        assert scope.tool_names == set()
        # Cannot invoke ANY agent or tool
        assert scope.can_invoke_agent(uuid.uuid4()) is False
        assert scope.can_invoke_tool("create_agent") is False

    async def test_member_with_department_loads_dept_scope(self, db, test_org):
        """MEMBER assigned to dept inherits the dept's grants."""
        dept = await _make_department(db, test_org.id, "Sales")
        agent = await _make_agent(db, test_org.id, dept.id, "Lead Scorer")
        member = await _make_member_user(db, test_org.id, dept.id)

        # Grant the agent to the dept
        admin_service = ScopeService(db, test_org.id, actor_user_id=member.id)
        await admin_service.grant_agent(dept.id, agent.id)
        await admin_service.grant_tool(dept.id, "assign_task")
        await db.flush()

        # Now resolve scope for the member
        service = ScopeService(db, test_org.id)
        scope = await service.resolve_scope_for_user(member)

        assert scope.is_org_wide is False
        assert scope.department_id == dept.id
        assert agent.id in scope.agent_ids
        assert "assign_task" in scope.tool_names
        # Confirm can_invoke methods work
        assert scope.can_invoke_agent(agent.id) is True
        assert scope.can_invoke_agent(uuid.uuid4()) is False  # different agent
        assert scope.can_invoke_tool("assign_task") is True
        assert scope.can_invoke_tool("create_agent") is False


# ─────────────────────────────────────────────────────────────────────────────
# TestGrantRevoke
# ─────────────────────────────────────────────────────────────────────────────


class TestGrantRevoke:
    async def test_grant_agent_creates_permission(self, db, test_org, test_user):
        dept = await _make_department(db, test_org.id)
        agent = await _make_agent(db, test_org.id, dept.id)

        service = ScopeService(db, test_org.id, actor_user_id=test_user.id)
        await service.grant_agent(dept.id, agent.id)
        await db.flush()

        result = await db.execute(
            select(DepartmentAgentPermission).where(
                DepartmentAgentPermission.department_id == dept.id,
                DepartmentAgentPermission.agent_id == agent.id,
            )
        )
        perm = result.scalar_one()
        assert perm.granted_by_user_id == test_user.id

    async def test_grant_agent_is_idempotent(self, db, test_org, test_user):
        dept = await _make_department(db, test_org.id)
        agent = await _make_agent(db, test_org.id, dept.id)
        service = ScopeService(db, test_org.id, actor_user_id=test_user.id)

        # Grant twice — second is no-op (ON CONFLICT DO NOTHING)
        await service.grant_agent(dept.id, agent.id)
        await service.grant_agent(dept.id, agent.id)
        await db.flush()

        result = await db.execute(
            select(DepartmentAgentPermission).where(
                DepartmentAgentPermission.department_id == dept.id,
                DepartmentAgentPermission.agent_id == agent.id,
            )
        )
        perms = result.scalars().all()
        assert len(perms) == 1

    async def test_revoke_agent_removes_permission_immediately(
        self, db, test_org, test_user
    ):
        """The promise: revokes have effect on the next request (no cache)."""
        dept = await _make_department(db, test_org.id)
        agent = await _make_agent(db, test_org.id, dept.id)
        member = await _make_member_user(db, test_org.id, dept.id)

        admin_service = ScopeService(db, test_org.id, actor_user_id=test_user.id)
        await admin_service.grant_agent(dept.id, agent.id)
        await db.flush()

        # Verify member has access right now
        scope_before = await admin_service.resolve_scope_for_user(member)
        assert agent.id in scope_before.agent_ids

        # Revoke
        await admin_service.revoke_agent(dept.id, agent.id)
        await db.flush()

        # Re-resolve — must reflect the revocation immediately
        scope_after = await admin_service.resolve_scope_for_user(member)
        assert agent.id not in scope_after.agent_ids

    async def test_grant_tool_and_revoke_tool(self, db, test_org, test_user):
        dept = await _make_department(db, test_org.id)
        service = ScopeService(db, test_org.id, actor_user_id=test_user.id)

        await service.grant_tool(dept.id, "create_agent")
        await db.flush()

        result = await db.execute(
            select(DepartmentToolPermission).where(
                DepartmentToolPermission.department_id == dept.id,
                DepartmentToolPermission.tool_name == "create_agent",
            )
        )
        assert result.scalar_one().tool_name == "create_agent"

        await service.revoke_tool(dept.id, "create_agent")
        await db.flush()

        result = await db.execute(
            select(DepartmentToolPermission).where(
                DepartmentToolPermission.department_id == dept.id,
                DepartmentToolPermission.tool_name == "create_agent",
            )
        )
        assert result.scalar_one_or_none() is None


# ─────────────────────────────────────────────────────────────────────────────
# TestCrossOrgBlocked — critical security property
# ─────────────────────────────────────────────────────────────────────────────


class TestCrossOrgBlocked:
    """A department in Org A cannot be granted an agent from Org B."""

    async def test_grant_agent_from_other_org_is_rejected(
        self, db, test_org, second_org, test_user
    ):
        # Create dept in test_org
        dept_a = await _make_department(db, test_org.id, "MarketingA")
        # Create agent in second_org (different tenant!)
        agent_b = await _make_agent(db, second_org.id, None, "RogueAgent")
        await db.flush()

        # Attempt to grant agent_b to dept_a — should fail
        service = ScopeService(db, test_org.id, actor_user_id=test_user.id)
        with pytest.raises((ValueError, Exception)) as exc:
            await service.grant_agent(dept_a.id, agent_b.id)
            await db.flush()
        # The agent will be 404 (different org filter) or cross-org error
        msg = str(exc.value).lower()
        assert "not found" in msg or "cross-org" in msg or "different organizations" in msg

    async def test_grant_to_department_from_other_org_is_rejected(
        self, db, test_org, second_org, test_user
    ):
        dept_b = await _make_department(db, second_org.id, "OtherOrgDept")
        agent_a = await _make_agent(db, test_org.id, None, "OurAgent")
        await db.flush()

        # As test_org admin, try to grant our agent to other org's dept
        service = ScopeService(db, test_org.id, actor_user_id=test_user.id)
        with pytest.raises(Exception):
            await service.grant_agent(dept_b.id, agent_a.id)
            await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# TestAuditOnScopeChanges
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditOnScopeChanges:
    async def test_grant_agent_creates_audit_entry(self, db, test_org, test_user):
        dept = await _make_department(db, test_org.id)
        agent = await _make_agent(db, test_org.id, dept.id)
        service = ScopeService(db, test_org.id, actor_user_id=test_user.id)

        await service.grant_agent(dept.id, agent.id)
        await db.flush()

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.MCP_PERMISSION_GRANTED,
                AuditLog.actor_user_id == test_user.id,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.resource_id == dept.id
        assert entry.context["scope_type"] == "agent"
        assert entry.context["agent_id"] == str(agent.id)

    async def test_revoke_agent_creates_audit_entry(self, db, test_org, test_user):
        dept = await _make_department(db, test_org.id)
        agent = await _make_agent(db, test_org.id, dept.id)
        service = ScopeService(db, test_org.id, actor_user_id=test_user.id)

        await service.grant_agent(dept.id, agent.id)
        await service.revoke_agent(dept.id, agent.id)
        await db.flush()

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.MCP_PERMISSION_REVOKED,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1


# ─────────────────────────────────────────────────────────────────────────────
# TestBulkReplace
# ─────────────────────────────────────────────────────────────────────────────


class TestBulkReplace:
    async def test_replace_department_scope_wipes_and_rebuilds(
        self, db, test_org, test_user
    ):
        dept = await _make_department(db, test_org.id)
        agent1 = await _make_agent(db, test_org.id, dept.id, "A1")
        agent2 = await _make_agent(db, test_org.id, dept.id, "A2")
        agent3 = await _make_agent(db, test_org.id, dept.id, "A3")
        service = ScopeService(db, test_org.id, actor_user_id=test_user.id)

        # First state: agent1 + tool1
        await service.grant_agent(dept.id, agent1.id)
        await service.grant_tool(dept.id, "tool_one")
        await db.flush()

        # Replace with agent2 + agent3 + tool2 + tool3
        await service.replace_department_scope(
            dept.id,
            agent_ids=[agent2.id, agent3.id],
            tool_names=["tool_two", "tool_three"],
        )
        await db.flush()

        # Verify final state
        agents_result = await db.execute(
            select(DepartmentAgentPermission.agent_id).where(
                DepartmentAgentPermission.department_id == dept.id
            )
        )
        final_agents = set(agents_result.scalars().all())
        assert final_agents == {agent2.id, agent3.id}
        assert agent1.id not in final_agents  # the original was wiped

        tools_result = await db.execute(
            select(DepartmentToolPermission.tool_name).where(
                DepartmentToolPermission.department_id == dept.id
            )
        )
        final_tools = set(tools_result.scalars().all())
        assert final_tools == {"tool_two", "tool_three"}

    async def test_replace_rejects_cross_org_agents(
        self, db, test_org, second_org, test_user
    ):
        dept_a = await _make_department(db, test_org.id)
        agent_b = await _make_agent(db, second_org.id, None, "Foreign")
        service = ScopeService(db, test_org.id, actor_user_id=test_user.id)

        with pytest.raises(ValueError) as exc:
            await service.replace_department_scope(
                dept_a.id,
                agent_ids=[agent_b.id],
                tool_names=[],
            )
        assert "another org" in str(exc.value).lower() or "non-existent" in str(exc.value).lower()
