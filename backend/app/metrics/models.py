import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MetricPeriod(str, enum.Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"
    __table_args__ = (
        UniqueConstraint("agent_id", "period", "period_start", name="uq_perf_agent_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    period: Mapped[MetricPeriod] = mapped_column(nullable=False)
    period_start: Mapped[datetime] = mapped_column(nullable=False)
    period_end: Mapped[datetime] = mapped_column(nullable=False)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, default=0)
    avg_response_ms: Mapped[float | None] = mapped_column(Numeric(12, 2))
    success_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    uptime_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    token_usage: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    custom_kpis: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    agent = relationship("Agent")
