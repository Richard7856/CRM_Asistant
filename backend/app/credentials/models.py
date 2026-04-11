"""
Credential model — stores API keys and secrets for agent tool integrations.

Secrets are stored as-is in the DB (encryption at rest via PostgreSQL).
The API layer NEVER returns the full secret — only a masked preview (last 4 chars).
When agents need the credential at runtime, the worker reads it directly from DB.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
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
    # The actual secret value — never exposed via API responses
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
