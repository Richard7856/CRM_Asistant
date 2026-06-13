"""
P0.7b — data retention tests.

- Eligible registry + policy CRUD (create/update/list/delete) via the admin API.
- Allowlist enforced (non-eligible table rejected) + role enforcement.
- purge_expired_data: deletes rows past the window, keeps fresh ones, audits the
  purge, and is opt-in (no policy → nothing deleted).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.auth.models import User, UserRole
from app.auth.service import create_access_token, hash_password
from app.compliance.models import RetentionPolicy
from app.compliance.service import purge_expired_data
from app.core.database import Base
from app.notifications.models import Notification, NotificationType


def _member_headers(user: User, org_id: uuid.UUID) -> dict[str, str]:
    token, _ = create_access_token(user.id, org_id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


async def _make_member(db, org_id) -> User:
    member = User(
        email=f"member-{uuid.uuid4().hex[:8]}@test.io",
        password_hash=hash_password("Test1234"),
        full_name="Miembro",
        role=UserRole.MEMBER,
        organization_id=org_id,
    )
    db.add(member)
    await db.flush()
    return member


# ─── Eligible + CRUD ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_eligible_lists_allowlist(client, auth_headers):
    resp = await client.get(
        "/api/v1/admin/compliance/retention/eligible", headers=auth_headers
    )
    assert resp.status_code == 200
    eligible = resp.json()["eligible"]
    tables = {e["table"] for e in eligible}
    assert "audit_log" in tables
    assert "notifications" in tables
    # core data must never be retention-eligible
    assert "users" not in tables and "credentials" not in tables
    audit_entry = next(e for e in eligible if e["table"] == "audit_log")
    assert audit_entry["recommended_days"] == 2555


@pytest.mark.asyncio
async def test_upsert_creates_then_updates(client, auth_headers, db, test_org):
    create = await client.put(
        "/api/v1/admin/compliance/retention/policies",
        headers=auth_headers,
        json={"table_name": "notifications", "retention_days": 90, "is_enabled": True},
    )
    assert create.status_code == 200
    assert create.json()["retention_days"] == 90

    update = await client.put(
        "/api/v1/admin/compliance/retention/policies",
        headers=auth_headers,
        json={"table_name": "notifications", "retention_days": 30, "is_enabled": False},
    )
    assert update.status_code == 200
    assert update.json()["retention_days"] == 30
    assert update.json()["is_enabled"] is False

    # Upsert, not duplicate: still exactly one policy for (org, notifications).
    count = (
        await db.execute(
            select(func.count())
            .select_from(RetentionPolicy)
            .where(
                RetentionPolicy.organization_id == test_org.id,
                RetentionPolicy.table_name == "notifications",
            )
        )
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_upsert_rejects_non_eligible_table(client, auth_headers):
    resp = await client.put(
        "/api/v1/admin/compliance/retention/policies",
        headers=auth_headers,
        json={"table_name": "users", "retention_days": 30, "is_enabled": True},
    )
    assert resp.status_code == 400  # core data is not retention-eligible


@pytest.mark.asyncio
async def test_upsert_requires_owner(client, db, test_org):
    member = await _make_member(db, test_org.id)
    resp = await client.put(
        "/api/v1/admin/compliance/retention/policies",
        headers=_member_headers(member, test_org.id),
        json={"table_name": "notifications", "retention_days": 30, "is_enabled": True},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_and_delete_policy(client, auth_headers):
    created = await client.put(
        "/api/v1/admin/compliance/retention/policies",
        headers=auth_headers,
        json={"table_name": "activity_logs", "retention_days": 60, "is_enabled": True},
    )
    policy_id = created.json()["id"]

    listed = await client.get(
        "/api/v1/admin/compliance/retention/policies", headers=auth_headers
    )
    assert listed.status_code == 200
    assert any(p["id"] == policy_id for p in listed.json())

    deleted = await client.delete(
        f"/api/v1/admin/compliance/retention/policies/{policy_id}", headers=auth_headers
    )
    assert deleted.status_code == 204


# ─── Purge ────────────────────────────────────────────────────────────────────


def _notif(org_id, *, created_at, title="n") -> Notification:
    return Notification(
        organization_id=org_id,
        title=title,
        notification_type=NotificationType.SYSTEM,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_purge_deletes_old_keeps_fresh_and_audits(db, test_org):
    org_id = test_org.id
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # notifications.created_at is tz-naive
    db.add_all([
        _notif(org_id, created_at=now - timedelta(days=100), title="old"),
        _notif(org_id, created_at=now - timedelta(days=1), title="fresh"),
    ])
    db.add(
        RetentionPolicy(
            organization_id=org_id,
            table_name="notifications",
            retention_days=30,
            is_enabled=True,
        )
    )
    await db.flush()

    total = await purge_expired_data(db)
    assert total == 1  # only the 100-day-old one

    notifs = Base.metadata.tables["notifications"]
    remaining = (
        await db.execute(
            select(func.count()).select_from(notifs).where(notifs.c.organization_id == org_id)
        )
    ).scalar_one()
    assert remaining == 1  # the fresh one survives

    audit = Base.metadata.tables["audit_log"]
    purged_events = (
        await db.execute(
            select(func.count())
            .select_from(audit)
            .where(
                audit.c.organization_id == org_id,
                audit.c.event_type == "RETENTION_PURGED",
            )
        )
    ).scalar_one()
    assert purged_events == 1


@pytest.mark.asyncio
async def test_purge_is_opt_in(db, test_org):
    """No policy → nothing is deleted, even for old rows."""
    org_id = test_org.id
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # notifications.created_at is tz-naive
    db.add(_notif(org_id, created_at=now - timedelta(days=999), title="ancient"))
    await db.flush()

    total = await purge_expired_data(db)
    assert total == 0

    notifs = Base.metadata.tables["notifications"]
    remaining = (
        await db.execute(
            select(func.count()).select_from(notifs).where(notifs.c.organization_id == org_id)
        )
    ).scalar_one()
    assert remaining == 1  # kept — retention is opt-in


@pytest.mark.asyncio
async def test_disabled_policy_does_not_purge(db, test_org):
    org_id = test_org.id
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # notifications.created_at is tz-naive
    db.add(_notif(org_id, created_at=now - timedelta(days=100), title="old"))
    db.add(
        RetentionPolicy(
            organization_id=org_id,
            table_name="notifications",
            retention_days=30,
            is_enabled=False,  # disabled → skipped
        )
    )
    await db.flush()
    assert await purge_expired_data(db) == 0
