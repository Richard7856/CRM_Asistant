"""
MCP Router endpoint + admin endpoints — P0.3.2/.3 integration tests.

Verifies the gateway logic: identify user → resolve scope → audit → dispatch.
Covers happy paths AND every denial path (each generates an audit entry).
"""

import uuid

from sqlalchemy import select

from app.agents.models import Agent, AgentOrigin, AgentStatus, Role, RoleLevel
from app.audit.models import AuditEventType, AuditLog
from app.auth.models import User, UserRole
from app.auth.service import create_access_token, hash_password
from app.departments.models import Department
from app.mcp.models import DepartmentAgentPermission, DepartmentToolPermission
from app.tasks.models import Task


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _make_department(db, org_id, name="Sales"):
    suffix = uuid.uuid4().hex[:8]
    dept = Department(
        name=f"{name}-{suffix}",
        slug=f"{name.lower()}-{suffix}",
        organization_id=org_id,
    )
    db.add(dept)
    await db.flush()
    return dept


async def _make_supervisor_role(db) -> Role:
    """Roles are global (no org_id), but tests should share one supervisor role."""
    result = await db.execute(select(Role).where(Role.level == RoleLevel.SUPERVISOR))
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    role = Role(name="Supervisor", level=RoleLevel.SUPERVISOR, description="Test supervisor role")
    db.add(role)
    await db.flush()
    return role


async def _make_supervisor_agent(db, org_id, dept_id, name="Director"):
    role = await _make_supervisor_role(db)
    agent = Agent(
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}",
        origin=AgentOrigin.INTERNAL,
        status=AgentStatus.ACTIVE,
        organization_id=org_id,
        department_id=dept_id,
        role_id=role.id,
    )
    db.add(agent)
    await db.flush()
    return agent


async def _make_member(db, org_id, dept_id=None):
    user = User(
        email=f"member-{uuid.uuid4().hex[:8]}@test.io",
        password_hash=hash_password("Test1234"),
        full_name="Member",
        role=UserRole.MEMBER,
        organization_id=org_id,
        department_id=dept_id,
    )
    db.add(user)
    await db.flush()
    return user


def _auth_headers(user: User, org_id: uuid.UUID) -> dict:
    token, _ = create_access_token(user.id, org_id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# TestRouteEndpoint — POST /api/v1/mcp/route
# ─────────────────────────────────────────────────────────────────────────────


class TestRouteEndpoint:
    async def test_owner_with_target_dept_routes_successfully(
        self, client, db, test_org, test_user, auth_headers
    ):
        """OWNER specifies a target dept, supervisor exists, task gets created."""
        dept = await _make_department(db, test_org.id, "Marketing")
        supervisor = await _make_supervisor_agent(db, test_org.id, dept.id, "Marketing Director")

        response = await client.post(
            "/api/v1/mcp/route",
            headers=auth_headers,
            json={
                "query": "Genera reporte semanal de campañas",
                "target_department_id": str(dept.id),
            },
        )
        assert response.status_code == 202
        body = response.json()
        assert body["department_id"] == str(dept.id)
        assert body["supervisor_agent_id"] == str(supervisor.id)
        assert "supervisor" in body["message"].lower()

        # Verify task was created and assigned to the supervisor
        task_id = uuid.UUID(body["task_id"])
        task = await db.get(Task, task_id)
        assert task is not None
        assert task.assigned_to == supervisor.id
        assert task.department_id == dept.id

    async def test_owner_without_dept_and_no_target_returns_400(
        self, client, db, test_org, auth_headers
    ):
        """OWNER without department must specify target_department_id."""
        # test_user is OWNER and has no department_id by default
        response = await client.post(
            "/api/v1/mcp/route",
            headers=auth_headers,
            json={"query": "do something"},
        )
        assert response.status_code == 400
        assert "target_department_id" in response.json()["detail"]

    async def test_member_without_dept_returns_403(self, client, db, test_org):
        member = await _make_member(db, test_org.id, dept_id=None)
        headers = _auth_headers(member, test_org.id)

        response = await client.post(
            "/api/v1/mcp/route",
            headers=headers,
            json={"query": "anything"},
        )
        assert response.status_code == 403
        assert "departamento" in response.json()["detail"].lower()

    async def test_member_routes_to_own_dept_supervisor(self, client, db, test_org):
        dept = await _make_department(db, test_org.id, "MarketingMember")
        supervisor = await _make_supervisor_agent(db, test_org.id, dept.id)
        member = await _make_member(db, test_org.id, dept.id)
        headers = _auth_headers(member, test_org.id)

        # Grant the supervisor to the member's dept (scope)
        db.add(DepartmentAgentPermission(
            department_id=dept.id,
            agent_id=supervisor.id,
            granted_by_user_id=member.id,
        ))
        await db.flush()

        response = await client.post(
            "/api/v1/mcp/route",
            headers=headers,
            json={"query": "Hazme un análisis de la campaña Q3"},
        )
        assert response.status_code == 202
        assert response.json()["supervisor_agent_id"] == str(supervisor.id)

    async def test_member_cannot_target_other_department(self, client, db, test_org):
        dept_own = await _make_department(db, test_org.id, "MemberOwn")
        dept_other = await _make_department(db, test_org.id, "MemberOther")
        await _make_supervisor_agent(db, test_org.id, dept_other.id)
        member = await _make_member(db, test_org.id, dept_own.id)
        headers = _auth_headers(member, test_org.id)

        response = await client.post(
            "/api/v1/mcp/route",
            headers=headers,
            json={
                "query": "x",
                "target_department_id": str(dept_other.id),
            },
        )
        assert response.status_code == 403
        assert "owner" in response.json()["detail"].lower() or "admin" in response.json()["detail"].lower()

    async def test_route_with_nonexistent_dept_returns_404(
        self, client, db, test_org, auth_headers
    ):
        response = await client.post(
            "/api/v1/mcp/route",
            headers=auth_headers,
            json={
                "query": "anything",
                "target_department_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 404

    async def test_dept_without_supervisor_returns_503(
        self, client, db, test_org, auth_headers
    ):
        dept = await _make_department(db, test_org.id, "Empty")
        # No supervisor agent created

        response = await client.post(
            "/api/v1/mcp/route",
            headers=auth_headers,
            json={
                "query": "x",
                "target_department_id": str(dept.id),
            },
        )
        assert response.status_code == 503
        assert "supervisor" in response.json()["detail"].lower()

    async def test_member_supervisor_not_in_scope_returns_403(self, client, db, test_org):
        """Member is in dept, dept has supervisor, but supervisor not granted to dept scope."""
        dept = await _make_department(db, test_org.id, "ScopelessDept")
        await _make_supervisor_agent(db, test_org.id, dept.id)  # dept needs a head; intentionally not scoped
        member = await _make_member(db, test_org.id, dept.id)
        headers = _auth_headers(member, test_org.id)

        # IMPORTANT: do NOT grant the supervisor to the dept's scope
        # → resolve_scope_for_user returns empty agent_ids
        # → scope.can_invoke_agent(supervisor.id) is False
        response = await client.post(
            "/api/v1/mcp/route",
            headers=headers,
            json={"query": "x"},
        )
        assert response.status_code == 403
        assert "scope" in response.json()["detail"].lower() or "permisos" in response.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# TestRouteAudit — every route attempt generates an audit entry
# ─────────────────────────────────────────────────────────────────────────────


class TestRouteAudit:
    async def test_successful_route_generates_audit_requested(
        self, client, db, test_org, auth_headers
    ):
        dept = await _make_department(db, test_org.id)
        supervisor = await _make_supervisor_agent(db, test_org.id, dept.id)

        await client.post(
            "/api/v1/mcp/route",
            headers=auth_headers,
            json={"query": "Genera reporte", "target_department_id": str(dept.id)},
        )

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.MCP_ROUTE_REQUESTED,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.context["department_id"] == str(dept.id)
        assert entry.context["supervisor_id"] == str(supervisor.id)
        # Query was hashed (privacy)
        assert entry.input_hash is not None and len(entry.input_hash) == 64

    async def test_denied_route_generates_audit_denied(self, client, db, test_org):
        member = await _make_member(db, test_org.id, dept_id=None)
        headers = _auth_headers(member, test_org.id)

        await client.post(
            "/api/v1/mcp/route",
            headers=headers,
            json={"query": "rejected query"},
        )

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.MCP_ROUTE_DENIED,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        assert entries[0].context["reason"] == "member_without_department"


# ─────────────────────────────────────────────────────────────────────────────
# TestAdminScopeEndpoints — OWNER/ADMIN only
# ─────────────────────────────────────────────────────────────────────────────


class TestAdminScopeEndpoints:
    async def test_get_dept_scope_returns_current(
        self, client, db, test_org, auth_headers
    ):
        dept = await _make_department(db, test_org.id, "MarketingX")
        agent = await _make_supervisor_agent(db, test_org.id, dept.id)
        db.add(DepartmentAgentPermission(department_id=dept.id, agent_id=agent.id))
        db.add(DepartmentToolPermission(department_id=dept.id, tool_name="assign_task"))
        await db.flush()

        response = await client.get(
            f"/api/v1/admin/departments/{dept.id}/scopes",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["department_id"] == str(dept.id)
        assert str(agent.id) in body["agent_ids"]
        assert "assign_task" in body["tool_names"]

    async def test_put_dept_scope_replaces_all(
        self, client, db, test_org, auth_headers
    ):
        dept = await _make_department(db, test_org.id, "PutScope")
        a1 = await _make_supervisor_agent(db, test_org.id, dept.id, "A1")
        a2 = await _make_supervisor_agent(db, test_org.id, dept.id, "A2")
        # Pre-existing permission for a1 — must be wiped by PUT
        db.add(DepartmentAgentPermission(department_id=dept.id, agent_id=a1.id))
        await db.flush()

        response = await client.put(
            f"/api/v1/admin/departments/{dept.id}/scopes",
            headers=auth_headers,
            json={"agent_ids": [str(a2.id)], "tool_names": ["create_agent"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["agent_ids"] == [str(a2.id)]
        assert body["tool_names"] == ["create_agent"]

    async def test_grant_agent_endpoint(
        self, client, db, test_org, auth_headers
    ):
        dept = await _make_department(db, test_org.id)
        agent = await _make_supervisor_agent(db, test_org.id, dept.id)

        response = await client.post(
            f"/api/v1/admin/departments/{dept.id}/scopes/agents",
            headers=auth_headers,
            json={"agent_id": str(agent.id)},
        )
        assert response.status_code == 204

        # Verify in DB
        result = await db.execute(
            select(DepartmentAgentPermission).where(
                DepartmentAgentPermission.department_id == dept.id,
                DepartmentAgentPermission.agent_id == agent.id,
            )
        )
        assert result.scalar_one() is not None

    async def test_revoke_agent_endpoint(
        self, client, db, test_org, auth_headers
    ):
        dept = await _make_department(db, test_org.id)
        agent = await _make_supervisor_agent(db, test_org.id, dept.id)
        db.add(DepartmentAgentPermission(department_id=dept.id, agent_id=agent.id))
        await db.flush()

        response = await client.delete(
            f"/api/v1/admin/departments/{dept.id}/scopes/agents/{agent.id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        result = await db.execute(
            select(DepartmentAgentPermission).where(
                DepartmentAgentPermission.department_id == dept.id,
                DepartmentAgentPermission.agent_id == agent.id,
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_grant_tool_endpoint(self, client, db, test_org, auth_headers):
        dept = await _make_department(db, test_org.id)

        response = await client.post(
            f"/api/v1/admin/departments/{dept.id}/scopes/tools",
            headers=auth_headers,
            json={"tool_name": "create_agent"},
        )
        assert response.status_code == 204

        result = await db.execute(
            select(DepartmentToolPermission).where(
                DepartmentToolPermission.department_id == dept.id,
                DepartmentToolPermission.tool_name == "create_agent",
            )
        )
        assert result.scalar_one() is not None

    async def test_member_cannot_access_admin_endpoints(self, client, db, test_org):
        member = await _make_member(db, test_org.id)
        headers = _auth_headers(member, test_org.id)
        dept = await _make_department(db, test_org.id)

        # GET
        get_response = await client.get(
            f"/api/v1/admin/departments/{dept.id}/scopes",
            headers=headers,
        )
        assert get_response.status_code == 403

        # PUT
        put_response = await client.put(
            f"/api/v1/admin/departments/{dept.id}/scopes",
            headers=headers,
            json={"agent_ids": [], "tool_names": []},
        )
        assert put_response.status_code == 403

    async def test_admin_endpoint_respects_tenant_isolation(
        self, client, db, second_org, auth_headers
    ):
        """Owner of test_org cannot see scopes of second_org's departments."""
        other_dept = await _make_department(db, second_org.id, "OtherOrg")

        response = await client.get(
            f"/api/v1/admin/departments/{other_dept.id}/scopes",
            headers=auth_headers,
        )
        # NotFound (the dept doesn't exist in test_user's org)
        assert response.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# TestRevocationIsInstant — the headline promise of the landing
# ─────────────────────────────────────────────────────────────────────────────


class TestRevocationIsInstant:
    """
    'Permisos revocables al instante' — the landing's headline promise.
    Verifies no in-memory cache: revoking a permission has effect on the very
    next request.
    """

    async def test_revoke_takes_effect_on_next_request(self, client, db, test_org, auth_headers):
        dept = await _make_department(db, test_org.id, "RevokeTest")
        supervisor = await _make_supervisor_agent(db, test_org.id, dept.id)
        member = await _make_member(db, test_org.id, dept.id)
        member_headers = _auth_headers(member, test_org.id)

        # Grant scope so the member can route
        db.add(DepartmentAgentPermission(department_id=dept.id, agent_id=supervisor.id))
        await db.flush()
        # Need to commit-equivalent for the client to see — using same session, so flush is enough

        # First call: member can route
        r1 = await client.post(
            "/api/v1/mcp/route",
            headers=member_headers,
            json={"query": "first call"},
        )
        assert r1.status_code == 202

        # Revoke via admin endpoint (test_user is owner)
        r_revoke = await client.delete(
            f"/api/v1/admin/departments/{dept.id}/scopes/agents/{supervisor.id}",
            headers=auth_headers,
        )
        assert r_revoke.status_code == 204

        # Second call IMMEDIATELY: must fail with 403 (no cache)
        r2 = await client.post(
            "/api/v1/mcp/route",
            headers=member_headers,
            json={"query": "second call"},
        )
        assert r2.status_code == 403
