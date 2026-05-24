"""
Credential model — stores API keys and secrets for agent tool integrations.

Secrets are encrypted at-rest with Fernet (AES-128-CBC + HMAC-SHA256) using
a key in .env separate from the database. The API layer NEVER returns the full
secret — only a masked preview (last 4 chars). When agents need the credential
at runtime, use `CredentialService.get_credential_value()` which decrypts and
logs the access in `credential_access_log` for audit purposes.

CredentialAccessLog model — append-only audit trail of every credential read.
Required for enterprise compliance (LFPDPPP, SOC 2 Type II): every "who read
which secret when, in what context" is queryable.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CredentialType(str, enum.Enum):
    API_KEY = "api_key"
    OAUTH_TOKEN = "oauth_token"
    BEARER_TOKEN = "bearer_token"
    BASIC_AUTH = "basic_auth"
    CUSTOM = "custom"


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    credential_type: Mapped[CredentialType] = mapped_column(
        default=CredentialType.API_KEY
    )
    # Encrypted secret (Fernet ciphertext). Never exposed via API responses.
    # Read with CredentialService.get_credential_value() which decrypts + logs access.
    secret_value: Mapped[str] = mapped_column(Text, nullable=False)
    # Service this credential belongs to (e.g., "openai", "serper", "slack")
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Optional: restrict credential to a specific agent
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), index=True
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    # Last 4 chars of the secret for display — set on create/update
    secret_preview: Mapped[str] = mapped_column(String(20), default="")
    notes: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    agent = relationship("Agent", foreign_keys=[agent_id])
    access_logs = relationship(
        "CredentialAccessLog", back_populates="credential", cascade="all, delete-orphan"
    )


class CredentialAccessLog(Base):
    """
    Append-only audit trail of credential reads.

    Every call to CredentialService.get_credential_value() generates one row.
    Required by enterprise compliance: a customer must be able to query
    "who accessed credential X, when, and in what context".

    No UPDATE/DELETE in normal operation. Cleanup is by retention policy
    (configurable per tenant — see LFPDPPP compliance in ROADMAP P0.7).
    """

    __tablename__ = "credential_access_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    credential_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credentials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The agent that requested the credential (nullable when access was manual).
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), index=True
    )
    # The user that requested the credential (nullable when access was programmatic).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Free-form context for the access — e.g., "task_execution:task_<uuid>"
    # or "manual:owner_view". Helps explain WHY this credential was read.
    context: Mapped[str | None] = mapped_column(String(200))

    credential = relationship("Credential", back_populates="access_logs")
