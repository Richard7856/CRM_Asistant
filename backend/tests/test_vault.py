"""
Vault tests — verifies credential encryption at rest, access logging, and
fail-fast startup behavior.

This is THE critical compliance feature for enterprise: if these tests fail,
HDI does not get its credentials safely stored. Treat any failure here as
release-blocking.
"""


import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.credentials.encryption import Vault, get_vault, reset_vault_for_tests
from app.credentials.models import Credential, CredentialAccessLog, CredentialType
from app.credentials.schemas import CredentialCreate
from app.credentials.service import CredentialService


# ─────────────────────────────────────────────────────────────────────────────
# TestVaultClass — pure crypto round-trip
# ─────────────────────────────────────────────────────────────────────────────


class TestVaultClass:
    """The Vault wrapper around Fernet. No DB, no FastAPI — just crypto."""

    def test_encrypt_decrypt_roundtrip(self):
        key = Fernet.generate_key()
        vault = Vault(key)
        ciphertext = vault.encrypt("sk-this-is-a-secret")
        assert ciphertext != "sk-this-is-a-secret"
        assert vault.decrypt(ciphertext) == "sk-this-is-a-secret"

    def test_two_encryptions_of_same_input_produce_different_ciphertexts(self):
        """Fernet adds a random IV — same plaintext encrypts differently each time."""
        key = Fernet.generate_key()
        vault = Vault(key)
        c1 = vault.encrypt("identical")
        c2 = vault.encrypt("identical")
        assert c1 != c2
        # But both decrypt back to the same plaintext
        assert vault.decrypt(c1) == vault.decrypt(c2) == "identical"

    def test_decrypt_with_wrong_key_fails(self):
        vault_a = Vault(Fernet.generate_key())
        vault_b = Vault(Fernet.generate_key())
        ciphertext = vault_a.encrypt("secret")
        with pytest.raises(InvalidToken):
            vault_b.decrypt(ciphertext)

    def test_decrypt_tampered_ciphertext_fails(self):
        vault = Vault(Fernet.generate_key())
        ciphertext = vault.encrypt("secret")
        # Flip a single character in the middle of the ciphertext
        tampered = ciphertext[:20] + ("X" if ciphertext[20] != "X" else "Y") + ciphertext[21:]
        with pytest.raises(InvalidToken):
            vault.decrypt(tampered)


# ─────────────────────────────────────────────────────────────────────────────
# TestGetVault — singleton + fail-fast behavior
# ─────────────────────────────────────────────────────────────────────────────


class TestGetVault:
    def test_get_vault_returns_singleton(self):
        reset_vault_for_tests()
        v1 = get_vault()
        v2 = get_vault()
        assert v1 is v2

    def test_get_vault_raises_without_key(self, monkeypatch):
        """When VAULT_ENCRYPTION_KEY is not set, get_vault() must fail clearly."""
        from app import config
        reset_vault_for_tests()
        monkeypatch.setattr(config.settings, "vault_encryption_key", "")
        with pytest.raises(RuntimeError) as exc:
            get_vault()
        assert "VAULT_ENCRYPTION_KEY" in str(exc.value)

    def test_reset_vault_for_tests_works(self, monkeypatch):
        """The reset helper must actually clear the singleton — used by other tests."""
        from app import config
        # First get a vault, then reset, then verify a new one is created
        v1 = get_vault()
        reset_vault_for_tests()
        # Change the key — if reset worked, the new vault uses the new key
        new_key = Fernet.generate_key().decode()
        monkeypatch.setattr(config.settings, "vault_encryption_key", new_key)
        v2 = get_vault()
        assert v1 is not v2


# ─────────────────────────────────────────────────────────────────────────────
# TestCredentialEncryption — end-to-end through CredentialService
# ─────────────────────────────────────────────────────────────────────────────


class TestCredentialEncryption:
    """Verifies the secret is encrypted in DB and decryptable via service."""

    async def test_secret_value_is_encrypted_in_db(self, db, test_org):
        """After create, raw secret_value in DB must NOT match the plaintext."""
        service = CredentialService(db, test_org.id)
        plaintext = "sk-real-anthropic-key-1234567890"
        await service.create_credential(
            CredentialCreate(
                name="Anthropic Production Key",
                credential_type=CredentialType.API_KEY,
                secret_value=plaintext,
                service_name="anthropic",
            )
        )

        # Read raw from DB without going through the service
        result = await db.execute(select(Credential).where(Credential.name == "Anthropic Production Key"))
        cred = result.scalar_one()
        assert cred.secret_value != plaintext, (
            "secret_value in DB matches plaintext — encryption is broken!"
        )
        # Ciphertext should start with Fernet's signature byte (base64-encoded)
        assert cred.secret_value.startswith("gAAAAA"), (
            f"secret_value does not look like Fernet ciphertext: {cred.secret_value[:20]}"
        )
        # Preview is still the masked plaintext (last 4 chars)
        assert cred.secret_preview == "****7890"

    async def test_get_credential_value_returns_plaintext(self, db, test_org):
        service = CredentialService(db, test_org.id)
        plaintext = "sk-original-secret-abcdef"
        created = await service.create_credential(
            CredentialCreate(
                name="Test Cred",
                credential_type=CredentialType.API_KEY,
                secret_value=plaintext,
                service_name="test",
            )
        )

        retrieved = await service.get_credential_value(
            cred_id=created.id,
            context="test:read",
        )
        assert retrieved == plaintext

    async def test_update_credential_re_encrypts_new_secret(self, db, test_org):
        service = CredentialService(db, test_org.id)
        created = await service.create_credential(
            CredentialCreate(
                name="Rotate Me",
                credential_type=CredentialType.API_KEY,
                secret_value="old-secret-value",
                service_name="test",
            )
        )

        from app.credentials.schemas import CredentialUpdate
        await service.update_credential(
            created.id,
            CredentialUpdate(secret_value="new-secret-value-different"),
        )

        # The new value must be retrievable AND the DB must hold ciphertext
        new_plaintext = await service.get_credential_value(
            cred_id=created.id, context="test:after_update"
        )
        assert new_plaintext == "new-secret-value-different"

        result = await db.execute(select(Credential).where(Credential.id == created.id))
        cred = result.scalar_one()
        assert cred.secret_value != "new-secret-value-different"


# ─────────────────────────────────────────────────────────────────────────────
# TestAccessLog — every read creates an audit entry
# ─────────────────────────────────────────────────────────────────────────────


class TestAccessLog:
    async def test_get_credential_value_creates_access_log_entry(self, db, test_org):
        service = CredentialService(db, test_org.id)
        created = await service.create_credential(
            CredentialCreate(
                name="Audited Cred",
                credential_type=CredentialType.API_KEY,
                secret_value="some-secret",
                service_name="test",
            )
        )

        # Before reading, the log is empty for this credential
        result = await db.execute(
            select(CredentialAccessLog).where(
                CredentialAccessLog.credential_id == created.id
            )
        )
        assert result.scalars().all() == []

        await service.get_credential_value(
            cred_id=created.id,
            context="task_execution:task_abc123",
        )

        # After reading, exactly one log entry exists
        result = await db.execute(
            select(CredentialAccessLog).where(
                CredentialAccessLog.credential_id == created.id
            )
        )
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].context == "task_execution:task_abc123"

    async def test_multiple_reads_create_multiple_log_entries(self, db, test_org):
        service = CredentialService(db, test_org.id)
        created = await service.create_credential(
            CredentialCreate(
                name="Read Often",
                credential_type=CredentialType.API_KEY,
                secret_value="secret",
                service_name="test",
            )
        )

        for i in range(5):
            await service.get_credential_value(
                cred_id=created.id, context=f"read_{i}"
            )

        result = await db.execute(
            select(CredentialAccessLog).where(
                CredentialAccessLog.credential_id == created.id
            )
        )
        logs = result.scalars().all()
        assert len(logs) == 5
        # Contexts preserved
        assert {log.context for log in logs} == {f"read_{i}" for i in range(5)}

    async def test_access_log_records_agent_id_when_provided(self, db, test_org, internal_agent):
        service = CredentialService(db, test_org.id)
        created = await service.create_credential(
            CredentialCreate(
                name="Agent Cred",
                credential_type=CredentialType.API_KEY,
                secret_value="secret",
                service_name="test",
            )
        )

        await service.get_credential_value(
            cred_id=created.id,
            context="task_execution:foo",
            agent_id=internal_agent.id,
        )

        result = await db.execute(
            select(CredentialAccessLog).where(
                CredentialAccessLog.credential_id == created.id
            )
        )
        log = result.scalar_one()
        assert log.agent_id == internal_agent.id
        assert log.user_id is None

    async def test_access_log_records_user_id_when_provided(self, db, test_org, test_user):
        service = CredentialService(db, test_org.id)
        created = await service.create_credential(
            CredentialCreate(
                name="User Cred",
                credential_type=CredentialType.API_KEY,
                secret_value="secret",
                service_name="test",
            )
        )

        await service.get_credential_value(
            cred_id=created.id,
            context="manual:owner_view",
            user_id=test_user.id,
        )

        result = await db.execute(
            select(CredentialAccessLog).where(
                CredentialAccessLog.credential_id == created.id
            )
        )
        log = result.scalar_one()
        assert log.user_id == test_user.id
        assert log.agent_id is None


# ─────────────────────────────────────────────────────────────────────────────
# TestTenantIsolation — credentials AND their access logs are scoped per org
# ─────────────────────────────────────────────────────────────────────────────


class TestTenantIsolation:
    async def test_get_credential_value_from_other_org_raises_notfound(
        self, db, test_org, second_org
    ):
        # Create credential in second_org
        service_b = CredentialService(db, second_org.id)
        created_b = await service_b.create_credential(
            CredentialCreate(
                name="Other Org Cred",
                credential_type=CredentialType.API_KEY,
                secret_value="other-org-secret",
                service_name="test",
            )
        )

        # Try to read it as test_org — should fail
        service_a = CredentialService(db, test_org.id)
        from app.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await service_a.get_credential_value(
                cred_id=created_b.id,
                context="malicious_attempt",
            )

        # And the access log should NOT have an entry (we never decrypted)
        # — the audit_first-then-decrypt pattern still creates the log entry
        # only when the cred is found, because we check existence first.
        result = await db.execute(
            select(CredentialAccessLog).where(
                CredentialAccessLog.credential_id == created_b.id
            )
        )
        logs = result.scalars().all()
        assert len(logs) == 0, (
            f"Access log got an entry from a failed cross-org access — leak risk. Got {logs}"
        )
