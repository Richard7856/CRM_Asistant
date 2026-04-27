"""
Tenant isolation tests — the most important guarantee in the entire system.

Every CRM Agents customer is an Organization. The product CANNOT leak data
between organizations. This file verifies:

1. List endpoints only return resources from the caller's org
2. Detail endpoints return 404 (not 403) when the resource belongs to another
   org — we don't even leak existence
3. Delete endpoints return 404 for cross-org resources
4. New resources created always carry the caller's org_id

Each test creates resources in TWO orgs, then makes requests authenticated
as one and verifies it cannot see/touch the other's data.

If any of these tests fail in CI, BLOCK THE RELEASE. A leak between tenants
is the single worst-case scenario for an enterprise SaaS.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent, AgentOrigin, AgentStatus
from app.credentials.models import Credential, CredentialType
from app.departments.models import Department
from app.knowledge.models import KnowledgeChunk, KnowledgeDocument
from app.tasks.models import Task


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — create resources directly in a given org via the DB session
# ─────────────────────────────────────────────────────────────────────────────


async def _make_department(db: AsyncSession, org_id: uuid.UUID, name: str) -> Department:
    # Department.name and .slug are globally unique — we add a UUID suffix to
    # avoid collisions across orgs. (NOTE: the global uniqueness itself is
    # arguably a product bug — names should be unique per org. Tracked separately.)
    suffix = uuid.uuid4().hex[:8]
    dept = Department(
        name=f"{name}-{suffix}",
        slug=f"{name.lower()}-{suffix}",
        organization_id=org_id,
    )
    db.add(dept)
    await db.flush()
    await db.refresh(dept)
    return dept


async def _make_agent(db: AsyncSession, org_id: uuid.UUID, name: str) -> Agent:
    suffix = uuid.uuid4().hex[:8]
    agent = Agent(
        name=f"{name}-{suffix}",
        slug=f"{name.lower()}-{suffix}",
        origin=AgentOrigin.INTERNAL,
        status=AgentStatus.ACTIVE,
        organization_id=org_id,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


async def _make_task(db: AsyncSession, org_id: uuid.UUID, title: str) -> Task:
    task = Task(
        title=title,
        organization_id=org_id,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def _make_credential(
    db: AsyncSession, org_id: uuid.UUID, name: str, secret: str = "supersecret123"
) -> Credential:
    cred = Credential(
        name=name,
        credential_type=CredentialType.API_KEY,
        secret_value=secret,
        secret_preview=f"****{secret[-4:]}",
        service_name="openai",
        organization_id=org_id,
    )
    db.add(cred)
    await db.flush()
    await db.refresh(cred)
    return cred


async def _make_document(
    db: AsyncSession, org_id: uuid.UUID, title: str, created_by_user_id: uuid.UUID
) -> KnowledgeDocument:
    doc = KnowledgeDocument(
        title=title,
        description="Test document",
        organization_id=org_id,
        created_by_user_id=created_by_user_id,
    )
    db.add(doc)
    await db.flush()
    # A real document has chunks for full-text search to work
    chunk = KnowledgeChunk(
        document_id=doc.id,
        organization_id=org_id,
        chunk_index=0,
        content=f"Contenido confidencial de {title}",
    )
    db.add(chunk)
    await db.flush()
    await db.refresh(doc)
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# TestListEndpointsRespectIsolation
# ─────────────────────────────────────────────────────────────────────────────


class TestListEndpointsRespectIsolation:
    """When you ask for a list, you must NEVER see another org's resources."""

    async def test_agents_list_excludes_other_orgs_agents(
        self, client, db, test_org, second_org, auth_headers
    ):
        # Org A has 1 agent, Org B has 1 agent
        agent_a = await _make_agent(db, test_org.id, "AgentA")
        agent_b = await _make_agent(db, second_org.id, "AgentB")

        # Auth as Org A — must see only agent_a
        response = await client.get("/api/v1/agents/", headers=auth_headers)
        assert response.status_code == 200

        ids_returned = {item["id"] for item in response.json()["items"]}
        assert str(agent_a.id) in ids_returned
        assert str(agent_b.id) not in ids_returned

    async def test_departments_list_excludes_other_orgs_departments(
        self, client, db, test_org, second_org, auth_headers
    ):
        dept_a = await _make_department(db, test_org.id, "DeptA")
        dept_b = await _make_department(db, second_org.id, "DeptB")

        response = await client.get("/api/v1/departments/", headers=auth_headers)
        assert response.status_code == 200

        ids_returned = {item["id"] for item in response.json()["items"]}
        assert str(dept_a.id) in ids_returned
        assert str(dept_b.id) not in ids_returned

    async def test_tasks_list_excludes_other_orgs_tasks(
        self, client, db, test_org, second_org, auth_headers
    ):
        task_a = await _make_task(db, test_org.id, "Task A")
        task_b = await _make_task(db, second_org.id, "Task B")

        response = await client.get("/api/v1/tasks/", headers=auth_headers)
        assert response.status_code == 200

        ids_returned = {item["id"] for item in response.json()["items"]}
        assert str(task_a.id) in ids_returned
        assert str(task_b.id) not in ids_returned

    async def test_credentials_list_excludes_other_orgs_credentials(
        self, client, db, test_org, second_org, auth_headers
    ):
        cred_a = await _make_credential(db, test_org.id, "Cred A")
        cred_b = await _make_credential(db, second_org.id, "Cred B")

        response = await client.get("/api/v1/credentials/", headers=auth_headers)
        assert response.status_code == 200

        ids_returned = {item["id"] for item in response.json()["items"]}
        assert str(cred_a.id) in ids_returned
        assert str(cred_b.id) not in ids_returned

    async def test_knowledge_list_excludes_other_orgs_documents(
        self, client, db, test_org, second_org, test_user, second_user, auth_headers
    ):
        doc_a = await _make_document(db, test_org.id, "Doc A", test_user.id)
        doc_b = await _make_document(db, second_org.id, "Doc B", second_user.id)

        response = await client.get("/api/v1/knowledge/", headers=auth_headers)
        assert response.status_code == 200

        # Knowledge endpoint may return either {"items": [...]} or just a list —
        # handle both shapes
        body = response.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        ids_returned = {item["id"] for item in items}
        assert str(doc_a.id) in ids_returned
        assert str(doc_b.id) not in ids_returned


# ─────────────────────────────────────────────────────────────────────────────
# TestDetailEndpointsRespectIsolation
# ─────────────────────────────────────────────────────────────────────────────


class TestDetailEndpointsRespectIsolation:
    """
    GET /resource/{id} where id belongs to another org must return 404 — NOT 403.
    Returning 403 leaks the existence of the resource ("you exist but I won't show
    you"). 404 says "this doesn't exist for you", which is what we want.
    """

    async def test_agent_detail_returns_404_for_other_org_resource(
        self, client, db, second_org, auth_headers
    ):
        # Create agent in OTHER org, then try to read it as user of FIRST org
        other_org_agent = await _make_agent(db, second_org.id, "Hidden")

        response = await client.get(
            f"/api/v1/agents/{other_org_agent.id}", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_department_detail_returns_404_for_other_org_resource(
        self, client, db, second_org, auth_headers
    ):
        other_org_dept = await _make_department(db, second_org.id, "Hidden")

        response = await client.get(
            f"/api/v1/departments/{other_org_dept.id}", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_task_detail_returns_404_for_other_org_resource(
        self, client, db, second_org, auth_headers
    ):
        other_org_task = await _make_task(db, second_org.id, "Hidden Task")

        response = await client.get(
            f"/api/v1/tasks/{other_org_task.id}", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_credential_detail_returns_404_for_other_org_resource(
        self, client, db, second_org, auth_headers
    ):
        other_org_cred = await _make_credential(db, second_org.id, "Hidden Cred")

        response = await client.get(
            f"/api/v1/credentials/{other_org_cred.id}", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_knowledge_detail_returns_404_for_other_org_resource(
        self, client, db, second_org, second_user, auth_headers
    ):
        other_org_doc = await _make_document(
            db, second_org.id, "Hidden Doc", second_user.id
        )

        response = await client.get(
            f"/api/v1/knowledge/{other_org_doc.id}", headers=auth_headers
        )
        assert response.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# TestDeleteEndpointsRespectIsolation
# ─────────────────────────────────────────────────────────────────────────────


class TestDeleteEndpointsRespectIsolation:
    """
    DELETE /resource/{id} for another org's resource must NOT delete it.
    Verify both: (a) the request returns 404, AND (b) the resource still exists.
    """

    async def test_cannot_delete_another_orgs_agent(
        self, client, db, second_org, auth_headers
    ):
        other_agent = await _make_agent(db, second_org.id, "Survivor")
        agent_id = other_agent.id

        response = await client.delete(
            f"/api/v1/agents/{agent_id}", headers=auth_headers
        )
        assert response.status_code == 404

        # Resource MUST still exist in the DB
        # (Agent has no is_active flag — soft-delete uses the `status` enum.
        # We just verify the row still exists; the contents are untouched.)
        survivor = await db.get(Agent, agent_id)
        assert survivor is not None, "Agent was deleted across org boundary — DATA LEAK BUG"

    async def test_cannot_delete_another_orgs_credential(
        self, client, db, second_org, auth_headers
    ):
        other_cred = await _make_credential(db, second_org.id, "Survivor")
        cred_id = other_cred.id

        response = await client.delete(
            f"/api/v1/credentials/{cred_id}", headers=auth_headers
        )
        assert response.status_code == 404

        survivor = await db.get(Credential, cred_id)
        assert survivor is not None, "Credential deleted across org boundary — DATA LEAK BUG"

    async def test_cannot_delete_another_orgs_knowledge_doc(
        self, client, db, second_org, second_user, auth_headers
    ):
        other_doc = await _make_document(
            db, second_org.id, "Survivor Doc", second_user.id
        )
        doc_id = other_doc.id

        response = await client.delete(
            f"/api/v1/knowledge/{doc_id}", headers=auth_headers
        )
        assert response.status_code == 404

        survivor = await db.get(KnowledgeDocument, doc_id)
        assert survivor is not None, "Document deleted across org boundary — DATA LEAK BUG"


# ─────────────────────────────────────────────────────────────────────────────
# TestCreateRespectsOrgScoping
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateRespectsOrgScoping:
    """
    When a user creates a resource, the org_id must come from the JWT — NEVER
    from the request body. A user must not be able to "spoof" creating a
    resource in another org by manipulating the payload.
    """

    async def test_created_department_is_scoped_to_caller_org(
        self, client, db, test_org, auth_headers
    ):
        unique_name = f"NewDept-{uuid.uuid4().hex[:8]}"
        response = await client.post(
            "/api/v1/departments/",
            headers=auth_headers,
            json={"name": unique_name, "description": "Created in test"},
        )
        assert response.status_code in (200, 201)
        dept_id = uuid.UUID(response.json()["id"])

        # The response schema doesn't expose organization_id (correct — clients
        # don't need it). Verify directly in the DB that org_id was set from JWT.
        dept = await db.get(Department, dept_id)
        assert dept.organization_id == test_org.id

    async def test_created_credential_is_scoped_to_caller_org(
        self, client, db, test_org, auth_headers
    ):
        response = await client.post(
            "/api/v1/credentials/",
            headers=auth_headers,
            json={
                "name": f"TestCred-{uuid.uuid4().hex[:8]}",
                "credential_type": "api_key",
                "secret_value": "sk-fake1234567890",
                "service_name": "openai",
            },
        )
        assert response.status_code in (200, 201)
        cred_id = uuid.UUID(response.json()["id"])

        # Verify in DB that it has caller's org_id
        cred = await db.get(Credential, cred_id)
        assert cred.organization_id == test_org.id


# ─────────────────────────────────────────────────────────────────────────────
# TestSearchRespectsIsolation
# ─────────────────────────────────────────────────────────────────────────────


class TestSearchRespectsIsolation:
    """
    Knowledge search uses PostgreSQL full-text search — verify it never returns
    chunks from other orgs even if they match the query text.
    """

    async def test_search_does_not_leak_other_orgs_chunks(
        self, client, db, test_org, second_org, test_user, second_user, auth_headers
    ):
        # Both orgs have a doc containing the same word
        await _make_document(db, test_org.id, "Manual Org A", test_user.id)
        await _make_document(db, second_org.id, "Manual Org B", second_user.id)

        # Search for "confidencial" (in both docs' chunks) as Org A.
        # Note: parameter name is `q` (not `query`).
        response = await client.get(
            "/api/v1/knowledge/search?q=confidencial",
            headers=auth_headers,
        )
        assert response.status_code == 200
        results = response.json()

        # Every result must reference content from Org A only — NOT "Manual Org B"
        for result in results:
            assert "Manual Org B" not in str(result), (
                f"Search leaked Org B chunk into Org A results: {result}"
            )
