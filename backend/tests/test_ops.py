"""
P0.8 — ops + tech-debt tests.

Covers the pieces that close the operational gaps:
- /health does a real DB connectivity check.
- expire_overdue_approvals (the 6th worker's core) flips stale PENDING → EXPIRED + audits.
- Failed logins get audited (closing the rollback gap) when the email is a real user.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.approvals.models import (
    ApprovalRequest,
    ApprovalStatus,
    AutonomyLevel,
)
from app.approvals.service import expire_overdue_approvals
from app.auth.service import _write_login_failure
from app.core.database import Base


# ─── /health ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_reports_db_up(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["database"] == "up"


# ─── Approval expiration worker (core logic) ──────────────────────────────────


def _make_pending(org_id, agent_id, *, expires_at) -> ApprovalRequest:
    return ApprovalRequest(
        organization_id=org_id,
        agent_id=agent_id,
        action="DELETE:contact",
        action_input={"id": "123"},
        autonomy_level=AutonomyLevel.MANUAL,
        status=ApprovalStatus.PENDING,
        expires_at=expires_at,
    )


@pytest.mark.asyncio
async def test_expire_overdue_approvals_flips_and_audits(db, test_org, internal_agent):
    org_id = test_org.id  # capture before any expire — avoids a lazy-load outside greenlet
    now = datetime.now(timezone.utc)
    overdue = _make_pending(org_id, internal_agent.id, expires_at=now - timedelta(hours=1))
    fresh = _make_pending(org_id, internal_agent.id, expires_at=now + timedelta(hours=1))
    db.add_all([overdue, fresh])
    await db.flush()

    count = await expire_overdue_approvals(db)
    assert count == 1
    # expire_overdue_approvals mutates the ORM objects in-session, so they're current.
    assert overdue.status == ApprovalStatus.EXPIRED
    assert overdue.decided_at is not None
    assert fresh.status == ApprovalStatus.PENDING  # not yet due

    # The expiration is auditable.
    audit = Base.metadata.tables["audit_log"]
    logged = (
        await db.execute(
            select(func.count())
            .select_from(audit)
            .where(
                audit.c.organization_id == org_id,
                audit.c.event_type == "APPROVAL_EXPIRED",
            )
        )
    ).scalar_one()
    assert logged == 1


@pytest.mark.asyncio
async def test_expire_overdue_approvals_noop_when_none(db, test_org, internal_agent):
    now = datetime.now(timezone.utc)
    db.add(_make_pending(test_org.id, internal_agent.id, expires_at=now + timedelta(hours=2)))
    await db.flush()
    assert await expire_overdue_approvals(db) == 0


# ─── Failed-login audit ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_failed_login_audited_for_real_user(db, test_user, test_org):
    wrote = await _write_login_failure(db, test_user.email)
    assert wrote is True

    audit = Base.metadata.tables["audit_log"]
    logged = (
        await db.execute(
            select(func.count())
            .select_from(audit)
            .where(
                audit.c.organization_id == test_org.id,
                audit.c.event_type == "LOGIN_FAILURE",
                audit.c.actor_user_id == test_user.id,
            )
        )
    ).scalar_one()
    assert logged == 1


@pytest.mark.asyncio
async def test_failed_login_skipped_for_unknown_email(db):
    wrote = await _write_login_failure(db, f"ghost-{uuid.uuid4().hex}@nowhere.io")
    assert wrote is False
    audit = Base.metadata.tables["audit_log"]
    total = (await db.execute(select(func.count()).select_from(audit))).scalar_one()
    assert total == 0
