import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class InteractionChannel(str, enum.Enum):
    API_CALL = "api_call"
    MESSAGE_QUEUE = "message_queue"
    WEBHOOK = "webhook"
    INTERNAL_BUS = "internal_bus"
    DIRECT = "direct"


class AgentInteraction(Base):
    __tablename__ = "agent_interactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    to_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    channel: Mapped[InteractionChannel] = mapped_column(nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), index=True
    )
    payload_summary: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    from_agent = relationship("Agent", foreign_keys=[from_agent_id])
    to_agent = relationship("Agent", foreign_keys=[to_agent_id])
    task = relationship("Task")
