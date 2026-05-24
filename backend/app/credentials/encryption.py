"""
Vault — application-level encryption for credentials at rest.

Wraps Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` library.
The encryption key (`VAULT_ENCRYPTION_KEY`) lives in `.env`, separate from the
database. If the DB is compromised but the key is not, ciphertexts remain safe.

Why Fernet over alternatives (decision documented in DECISIONS.md):
- Fernet: stdlib-equivalent, simple, sufficient for MVP enterprise needs.
- AWS/GCP KMS: planned upgrade for Phase 5 when volume justifies the dependency.
- Per-tenant keys: planned for Phase 5+ if SOC 2 Type II requires it.

Usage:
    vault = get_vault()
    ciphertext = vault.encrypt("sk-real-api-key")
    plaintext = vault.decrypt(ciphertext)
"""

from cryptography.fernet import Fernet

from app.config import settings


class Vault:
    """Symmetric encryption wrapper for credentials at rest."""

    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string. Returns base64-encoded ciphertext (URL-safe)."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext. Raises InvalidToken if tampered."""
        return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


# Module-level singleton. Lazy-initialized so importing this module doesn't
# fail when the key isn't set (e.g., during test collection before fixtures run).
_vault: Vault | None = None


def get_vault() -> Vault:
    """
    Get the application's Vault instance.
    Raises RuntimeError if VAULT_ENCRYPTION_KEY is not set.

    The key must be a 32-byte base64-encoded value. Generate one with:
        python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
    """
    global _vault
    if _vault is None:
        key = settings.vault_encryption_key
        if not key:
            raise RuntimeError(
                "VAULT_ENCRYPTION_KEY no esta configurada. "
                "Generar con: python -c 'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())' "
                "y agregarla al archivo .env"
            )
        _vault = Vault(key.encode("utf-8"))
    return _vault


def reset_vault_for_tests() -> None:
    """Reset the singleton — only for use in test setup/teardown."""
    global _vault
    _vault = None
