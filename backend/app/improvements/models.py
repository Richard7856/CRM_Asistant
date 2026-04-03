import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.tasks.models import TaskPriority


class ImprovementStatus(str, enum.Enum):
    IDENTIFIED = "identified"
    PROPOSED = "proposed"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    DISMISSED = "dismissed"


class ImprovementPoint(Base):
    __tablename__ = "improvement_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    identified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id")
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[ImprovementStatus] = mapped_column(default=ImprovementStatus.IDENTIFIED)
    priority: Mapped[TaskPriority] = mapped_column(default=TaskPriority.MEDIUM)
    resolution: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent", foreign_keys=[agent_id])
    identifier = relationship("Agent", foreign_keys=[identified_by])
