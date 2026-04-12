"""
Notification model — alerts for human operators about autonomous agent actions.

Notifications are created by the lifecycle monitor (idle agent detection)
and by autonomous tool actions (agent created, department created).
Humans dismiss or act on them via the API.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class NotificationType(str, enum.Enum):
    AGENT_IDLE = "agent_idle"
    AGENT_CREATED = "agent_created"
    DEPARTMENT_CREATED = "department_created"
    TASK_ASSIGNED = "task_assigned"
    PROMPT_GENERATED = "prompt_generated"
    SYSTEM = "system"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    notification_type: Mapped[NotificationType] = mapped_column(nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    # URL for the frontend to navigate to when the user clicks the notification
    action_url: Mapped[str | None] = mapped_column(String(500))
    # Extra data for the notification (e.g. agent details, idle duration)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    organization = relationship("Organization", foreign_keys=[organization_id])
    agent = relationship("Agent", foreign_keys=[agent_id])
