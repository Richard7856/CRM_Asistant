"""
Audit log tests — verify every critical action generates an immutable entry.

If these tests pass, we have evidence that:
1. Every sensitive endpoint records an audit entry
2. Inputs/outputs are stored as SHA-256 hashes (not raw content)
3. UPDATE on audit_log is forbidden (trigger blocks it)
4. Tenant isolation works (Org A doesn't see Org B's audit log)
5. The export endpoint produces parseable CSV

If a test here fails in CI, it's release-blocking — compliance promises hinge on this.
"""

import csv
import io
import uuid

import pytest
from sqlalchemy import select, text

from app.audit.models import AuditEventType, AuditLog, AuditResult
from app.audit.service import _hash_payload, log_audit_event
from app.credentials.models import CredentialType
from app.credentials.schemas import CredentialCreate
from app.credentials.service import CredentialService


# ─────────────────────────────────────────────────────────────────────────────
# TestHashPayload — pure crypto helper
# ─────────────────────────────────────────────────────────────────────────────


class TestHashPayload:
    def test_hash_string_returns_64_char_hex(self):
        h = _hash_payload("hello world")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_dict_is_stable_across_key_orders(self):
        h1 = _hash_payload({"a": 1, "b": 2})
        h2 = _hash_payload({"b": 2, "a": 1})
        assert h1 == h2  # sort_keys ensures determinism

    def test_hash_different_inputs_produce_different_hashes(self):
        assert _hash_payload("a") != _hash_payload("b")

    def test_hash_none_returns_empty(self):
        assert _hash_payload(None) == ""

    def test_hash_complex_dict_works(self):
        payload = {"task_id": "abc", "agent": {"name": "X", "tools": [1, 2, 3]}}
        h = _hash_payload(payload)
        assert len(h) == 64


# ─────────────────────────────────────────────────────────────────────────────
# TestLogAuditEvent — the core helper
# ─────────────────────────────────────────────────────────────────────────────


class TestLogAuditEvent:
    async def test_creates_entry_with_minimal_args(self, db, test_org, test_user):
        entry = await log_audit_event(
            db,
            organization_id=test_org.id,
            event_type=AuditEventType.LOGIN_SUCCESS,
            actor_user_id=test_user.id,
        )
        assert entry.id is not None
        assert entry.event_type == AuditEventType.LOGIN_SUCCESS
        assert entry.organization_id == test_org.id
        assert entry.actor_user_id == test_user.id
        assert entry.result == AuditResult.SUCCESS
        assert entry.input_hash is None
        assert entry.output_hash is None

    async def test_input_and_output_are_hashed_not_stored_raw(self, db, test_org, test_user):
        sensitive = "very-secret-prompt-content"
        entry = await log_audit_event(
            db,
            organization_id=test_org.id,
            event_type=AuditEventType.TASK_EXECUTED,
            actor_user_id=test_user.id,
            input_payload=sensitive,
            output_payload="response-with-pii",
        )
        # Hashes are present and look right
        assert entry.input_hash and len(entry.input_hash) == 64
        assert entry.output_hash and len(entry.output_hash) == 64
        # Raw payload NEVER stored — even searching context for the string fails
        # (sanity: context is a dict, not bound to input/output)
        assert sensitive not in str(entry.context)

    async def test_context_dict_is_preserved(self, db, test_org, test_user):
        entry = await log_audit_event(
            db,
            organization_id=test_org.id,
            event_type=AuditEventType.LOGIN_SUCCESS,
            actor_user_id=test_user.id,
            context={"ip": "10.0.0.1", "user_agent": "Chrome/test"},
        )
        assert entry.context["ip"] == "10.0.0.1"
        assert entry.context["user_agent"] == "Chrome/test"


# ─────────────────────────────────────────────────────────────────────────────
# TestAppendOnlyEnforcement — the DB trigger
# ─────────────────────────────────────────────────────────────────────────────


class TestAppendOnlyEnforcement:
    """The DB trigger MUST block UPDATE — even with raw SQL."""

    async def test_update_on_audit_log_raises_db_exception(self, db, test_org, test_user):
        entry = await log_audit_event(
            db,
            organization_id=test_org.id,
            event_type=AuditEventType.LOGIN_SUCCESS,
            actor_user_id=test_user.id,
        )
        await db.flush()

        # Use a non-enum column (context JSONB) — the trigger fires BEFORE column
        # value validation, so any UPDATE must fail with the trigger's exception
        # regardless of the field being updated.
        with pytest.raises(Exception) as exc:
            await db.execute(
                text("UPDATE audit_log SET context = '{\"tampered\": true}'::jsonb WHERE id = :id"),
                {"id": entry.id},
            )
            await db.flush()
        # The trigger raises with a specific message; SQLAlchemy wraps it.
        assert "append-only" in str(exc.value).lower() or "forbidden" in str(exc.value).lower()


# ─────────────────────────────────────────────────────────────────────────────
# TestEndpointIntegration — verify each critical endpoint emits an audit entry
# ─────────────────────────────────────────────────────────────────────────────


class TestEndpointIntegration:
    async def test_login_success_creates_audit_entry(self, client, db, test_user):
        # test_user is created with password "Test1234"
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "Test1234"},
        )
        assert response.status_code == 200

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.LOGIN_SUCCESS,
                AuditLog.actor_user_id == test_user.id,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        assert entries[0].organization_id == test_user.organization_id

    async def test_logout_creates_audit_entry(self, client, db, test_user, auth_headers):
        response = await client.post("/api/v1/auth/logout", headers=auth_headers)
        assert response.status_code == 200

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.LOGOUT,
                AuditLog.actor_user_id == test_user.id,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1

    async def test_credential_create_generates_audit_event(
        self, db, test_org, test_user
    ):
        # Use service directly — same code path the router uses
        service = CredentialService(db, test_org.id, actor_user_id=test_user.id)
        created = await service.create_credential(
            CredentialCreate(
                name="Audit Test Cred",
                credential_type=CredentialType.API_KEY,
                secret_value="sk-audit-test",
                service_name="test",
            )
        )

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.CREDENTIAL_CREATED,
                AuditLog.resource_id == created.id,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.actor_user_id == test_user.id
        assert entry.resource_type == "credential"
        # Input payload was hashed
        assert entry.input_hash is not None and len(entry.input_hash) == 64
        # Raw secret value NEVER appears anywhere — only the preview
        assert "sk-audit-test" not in str(entry.context)

    async def test_credential_delete_generates_audit_event(
        self, db, test_org, test_user
    ):
        service = CredentialService(db, test_org.id, actor_user_id=test_user.id)
        created = await service.create_credential(
            CredentialCreate(
                name="To Delete",
                credential_type=CredentialType.API_KEY,
                secret_value="secret",
                service_name="test",
            )
        )
        await service.delete_credential(created.id)

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.CREDENTIAL_DELETED,
                AuditLog.resource_id == created.id,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1


# ─────────────────────────────────────────────────────────────────────────────
# TestTenantIsolation — Org A never sees Org B's audit log
# ─────────────────────────────────────────────────────────────────────────────


class TestTenantIsolation:
    async def test_org_a_query_excludes_org_b_audit_entries(
        self, db, test_org, second_org, test_user, second_user
    ):
        # Generate entries in both orgs
        await log_audit_event(
            db, organization_id=test_org.id,
            event_type=AuditEventType.LOGIN_SUCCESS,
            actor_user_id=test_user.id,
        )
        await log_audit_event(
            db, organization_id=second_org.id,
            event_type=AuditEventType.LOGIN_SUCCESS,
            actor_user_id=second_user.id,
        )

        # Query as Org A — must only see Org A
        from app.audit.service import AuditService
        service_a = AuditService(db, test_org.id)
        items_a, total_a = await service_a.list_events()
        assert total_a >= 1
        for entry in items_a:
            assert entry.organization_id == test_org.id

        # Query as Org B — must only see Org B
        service_b = AuditService(db, second_org.id)
        items_b, total_b = await service_b.list_events()
        assert total_b >= 1
        for entry in items_b:
            assert entry.organization_id == second_org.id


# ─────────────────────────────────────────────────────────────────────────────
# TestExportCSV — auditors get a usable file
# ─────────────────────────────────────────────────────────────────────────────


class TestExportCSV:
    async def test_export_csv_returns_valid_csv_with_headers(
        self, db, test_org, test_user
    ):
        # Generate a few entries
        for event in [AuditEventType.LOGIN_SUCCESS, AuditEventType.LOGOUT, AuditEventType.AGENT_CREATED]:
            await log_audit_event(
                db, organization_id=test_org.id,
                event_type=event,
                actor_user_id=test_user.id,
            )

        from app.audit.service import AuditService
        service = AuditService(db, test_org.id)
        csv_str = await service.export_csv()

        # Parse it back
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) >= 4  # 1 header + 3+ data rows
        header = rows[0]
        # Critical columns must be present for auditors
        for col in ["id", "occurred_at", "event_type", "result", "actor_user_id"]:
            assert col in header, f"CSV missing required column: {col}"

    async def test_export_csv_filters_by_event_type(self, db, test_org, test_user):
        await log_audit_event(
            db, organization_id=test_org.id,
            event_type=AuditEventType.LOGIN_SUCCESS,
            actor_user_id=test_user.id,
        )
        await log_audit_event(
            db, organization_id=test_org.id,
            event_type=AuditEventType.LOGOUT,
            actor_user_id=test_user.id,
        )

        from app.audit.service import AuditService
        service = AuditService(db, test_org.id)
        csv_str = await service.export_csv(event_type=AuditEventType.LOGOUT)

        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        # All data rows must have event_type=auth.logout
        header = rows[0]
        et_idx = header.index("event_type")
        for row in rows[1:]:
            assert row[et_idx] == AuditEventType.LOGOUT.value


# ─────────────────────────────────────────────────────────────────────────────
# TestRoleGuard — only owners/admins can read the audit log
# ─────────────────────────────────────────────────────────────────────────────


class TestRoleGuard:
    """The endpoint must reject non-admin users — sensitive data."""

    async def test_owner_can_list_audit_events(self, client, auth_headers):
        # test_user is created as OWNER by default
        response = await client.get("/api/v1/audit-log/", headers=auth_headers)
        assert response.status_code == 200

    async def test_member_cannot_list_audit_events(
        self, client, db, test_org
    ):
        # Create a user with MEMBER role
        from app.auth.models import User, UserRole
        from app.auth.service import create_access_token, hash_password
        member = User(
            email=f"member-{uuid.uuid4().hex[:8]}@test.io",
            password_hash=hash_password("Test1234"),
            full_name="Member",
            role=UserRole.MEMBER,
            organization_id=test_org.id,
        )
        db.add(member)
        await db.flush()
        token, _ = create_access_token(member.id, test_org.id, member.role.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get("/api/v1/audit-log/", headers=headers)
        assert response.status_code == 403
