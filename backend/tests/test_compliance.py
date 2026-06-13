"""
P0.7 — LFPDPPP compliance tests.

Covers the data-subject rights:
- Data classification registry stays in sync with the schema (coverage test).
- Right of access: tenant + per-user export.
- Right to be forgotten: ordered tenant erasure (+ certificate) and user anonymization.
- Tenant isolation and role enforcement on every destructive path.
- Certificate immutability (DB trigger blocks UPDATE/DELETE).
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.audit.models import AuditEventType
from app.audit.service import log_audit_event
from app.auth.models import User, UserRole
from app.auth.service import create_access_token, hash_password
from app.compliance.classification import GLOBAL_TABLES, tenant_table_names
from app.compliance.models import (
    ErasureCertificate,
    ErasureMethod,
    ErasureSubjectType,
)
from app.core.database import Base
from app.departments.models import Department
from app.notifications.models import Notification, NotificationType
from app.tasks.models import Task, TaskStatus


async def _count(db, table_name: str, org_id: uuid.UUID) -> int:
    table = Base.metadata.tables[table_name]
    stmt = select(func.count()).select_from(table).where(table.c.organization_id == org_id)
    return int((await db.execute(stmt)).scalar_one())


def _member_headers(user: User, org_id: uuid.UUID) -> dict[str, str]:
    token, _ = create_access_token(user.id, org_id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def rich_tenant(db, test_org, test_user, internal_agent):
    """
    A tenant with data across many tables, deliberately wiring the agents↔departments
    cycle and an agent self-reference so erasure must run its null-breaker phase.
    """
    suffix = uuid.uuid4().hex[:8]
    dept = Department(
        name=f"Ventas {suffix}",
        slug=f"ventas-{suffix}",
        organization_id=test_org.id,
        head_agent_id=internal_agent.id,  # departments → agents
    )
    db.add(dept)
    await db.flush()

    internal_agent.department_id = dept.id          # agents → departments (cycle)
    internal_agent.created_by_agent_id = internal_agent.id  # self-reference
    await db.flush()

    task = Task(
        title="Reactivar clientes inactivos",
        organization_id=test_org.id,
        status=TaskStatus.PENDING,
        assigned_to=internal_agent.id,
        department_id=dept.id,
    )
    db.add(task)
    await db.flush()

    db.add(
        Notification(
            organization_id=test_org.id,
            title="Agente creado",
            notification_type=NotificationType.SYSTEM,
            agent_id=internal_agent.id,
        )
    )
    member = User(
        email=f"member-{suffix}@test.io",
        password_hash=hash_password("Test1234"),
        full_name="Miembro Equipo",
        role=UserRole.MEMBER,
        organization_id=test_org.id,
    )
    db.add(member)
    await db.flush()

    await log_audit_event(
        db,
        organization_id=test_org.id,
        event_type=AuditEventType.TASK_CREATED,
        resource_type="task",
        resource_id=task.id,
        actor_user_id=test_user.id,
    )
    await db.flush()

    return {"dept": dept, "task": task, "member": member, "agent": internal_agent}


# ─── Classification registry ──────────────────────────────────────────────────


def test_classification_covers_exactly_the_tenant_tables():
    """
    The registry must list every table with organization_id and nothing else.
    Fails loudly the day a new tenant table is added without wiring erasure/export.
    """
    org_tables = {
        name for name, table in Base.metadata.tables.items()
        if "organization_id" in table.c
    }
    # erasure_certificates carries organization_id as a snapshot, not as tenant data.
    assert org_tables - GLOBAL_TABLES == set(tenant_table_names())


@pytest.mark.asyncio
async def test_get_classification_endpoint(client, auth_headers):
    resp = await client.get(
        "/api/v1/admin/compliance/classification", headers=auth_headers
    )
    assert resp.status_code == 200
    tables = resp.json()["tables"]
    assert len(tables) == len(tenant_table_names())
    users_entry = next(t for t in tables if t["table"] == "users")
    assert users_entry["classification"] == "pii"
    assert "email" in users_entry["pii_columns"]


# ─── Export ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_tenant_returns_all_data(client, auth_headers, rich_tenant):
    resp = await client.get("/api/v1/admin/compliance/export", headers=auth_headers)
    assert resp.status_code == 200
    bundle = resp.json()
    assert bundle["manifest"]["scope"] == "tenant"
    # test_user + the seeded member = at least 2 users in the export.
    assert len(bundle["data"]["users"]) >= 2
    assert len(bundle["data"]["tasks"]) >= 1


@pytest.mark.asyncio
async def test_export_user_scoped_to_org(client, auth_headers, rich_tenant):
    member = rich_tenant["member"]
    resp = await client.get(
        f"/api/v1/admin/compliance/export/users/{member.id}", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["users"]) == 1
    assert data["users"][0]["email"] == member.email


# ─── Right to be forgotten: tenant ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_erase_tenant_deletes_everything_and_issues_certificate(
    client, auth_headers, db, test_org, rich_tenant
):
    # Sanity: data exists before erasure.
    assert await _count(db, "users", test_org.id) >= 2
    assert await _count(db, "tasks", test_org.id) >= 1

    resp = await client.request(
        "DELETE",
        "/api/v1/admin/compliance/erase-tenant",
        headers=auth_headers,
        json={"confirmation": test_org.slug},
    )
    assert resp.status_code == 200
    cert = resp.json()
    assert cert["subject_type"] == "tenant"
    assert cert["method"] == "ordered_delete"
    assert cert["total_rows_erased"] > 0
    assert cert["row_counts"]["users"] >= 2
    assert len(cert["content_hash"]) == 64

    # Everything is actually gone.
    for table_name in tenant_table_names():
        assert await _count(db, table_name, test_org.id) == 0
    orgs = Base.metadata.tables["organizations"]
    org_left = (
        await db.execute(
            select(func.count()).select_from(orgs).where(orgs.c.id == test_org.id)
        )
    ).scalar_one()
    assert org_left == 0

    # The certificate survives the org.
    cert_left = (
        await db.execute(
            select(ErasureCertificate).where(ErasureCertificate.id == uuid.UUID(cert["id"]))
        )
    ).scalar_one_or_none()
    assert cert_left is not None
    assert cert_left.subject_type == ErasureSubjectType.TENANT


@pytest.mark.asyncio
async def test_erase_tenant_wrong_confirmation_aborts(
    client, auth_headers, db, test_org, rich_tenant
):
    resp = await client.request(
        "DELETE",
        "/api/v1/admin/compliance/erase-tenant",
        headers=auth_headers,
        json={"confirmation": "no-es-el-slug"},
    )
    assert resp.status_code == 400
    # Nothing was deleted.
    assert await _count(db, "users", test_org.id) >= 2
    orgs = Base.metadata.tables["organizations"]
    org_left = (
        await db.execute(
            select(func.count()).select_from(orgs).where(orgs.c.id == test_org.id)
        )
    ).scalar_one()
    assert org_left == 1


@pytest.mark.asyncio
async def test_erase_tenant_does_not_touch_other_tenants(
    client, auth_headers, db, test_org, rich_tenant, second_org, second_user
):
    resp = await client.request(
        "DELETE",
        "/api/v1/admin/compliance/erase-tenant",
        headers=auth_headers,
        json={"confirmation": test_org.slug},
    )
    assert resp.status_code == 200
    # The second org is untouched.
    assert await _count(db, "users", second_org.id) == 1


@pytest.mark.asyncio
async def test_erase_tenant_requires_owner(client, db, test_org, rich_tenant):
    member = rich_tenant["member"]  # MEMBER role
    resp = await client.request(
        "DELETE",
        "/api/v1/admin/compliance/erase-tenant",
        headers=_member_headers(member, test_org.id),
        json={"confirmation": test_org.slug},
    )
    assert resp.status_code == 403
    assert await _count(db, "users", test_org.id) >= 2  # nothing deleted


# ─── Right to be forgotten: user (anonymization) ──────────────────────────────


@pytest.mark.asyncio
async def test_erase_user_anonymizes_in_place(
    client, auth_headers, db, test_org, rich_tenant
):
    member = rich_tenant["member"]
    member_id = member.id
    org_id = test_org.id
    original_email = member.email

    resp = await client.request(
        "DELETE",
        f"/api/v1/admin/compliance/erase-users/{member_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    cert = resp.json()
    assert cert["subject_type"] == "user"
    assert cert["method"] == "anonymize"
    assert cert["subject_user_id"] == str(member_id)

    # The repo anonymizes via a core UPDATE that bypasses the identity map, so the
    # in-session ORM object is stale. populate_existing forces the ORM to overwrite
    # it with the committed DB values. (Irrelevant in production — fresh session per request.)
    refreshed = (
        await db.execute(
            select(User)
            .where(User.id == member_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed.email != original_email
    assert refreshed.email.startswith("erased-")
    assert refreshed.full_name == "Usuario eliminado"
    assert refreshed.is_active is False

    # The anonymization is itself auditable (org survives).
    audit = Base.metadata.tables["audit_log"]
    logged = (
        await db.execute(
            select(func.count())
            .select_from(audit)
            .where(
                audit.c.organization_id == org_id,
                audit.c.event_type == "USER_ERASED",
            )
        )
    ).scalar_one()
    assert logged == 1


# ─── Certificate immutability ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_erasure_certificate_cannot_be_modified(db, test_org):
    cert = ErasureCertificate(
        organization_id=test_org.id,
        organization_name="X",
        organization_slug="x",
        subject_type=ErasureSubjectType.TENANT,
        method=ErasureMethod.ORDERED_DELETE,
        row_counts={},
        total_rows_erased=0,
        content_hash="0" * 64,
    )
    db.add(cert)
    await db.flush()

    # The DB trigger must reject any UPDATE on a certificate.
    with pytest.raises(Exception):
        await db.execute(
            text("UPDATE erasure_certificates SET total_rows_erased = 99 WHERE id = :i"),
            {"i": str(cert.id)},
        )
