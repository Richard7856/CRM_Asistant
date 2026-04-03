import uuid
from datetime import datetime

from sqlalchemy import cast, func, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent, AgentStatus
from app.core.pagination import PaginationParams
from app.metrics.models import MetricPeriod, PerformanceMetric
from app.tasks.models import Task, TaskStatus


class MetricRepository:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    def _scoped(self):
        return select(PerformanceMetric).where(PerformanceMetric.organization_id == self.org_id)

    async def list_all(
        self,
        pagination: PaginationParams,
        *,
        agent_id: uuid.UUID | None = None,
        department_id: uuid.UUID | None = None,
        period: MetricPeriod | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> tuple[list[PerformanceMetric], int]:
        query = self._scoped()
        count_base = select(func.count()).select_from(PerformanceMetric).where(
            PerformanceMetric.organization_id == self.org_id
        )

        if agent_id is not None:
            query = query.where(PerformanceMetric.agent_id == agent_id)
            count_base = count_base.where(PerformanceMetric.agent_id == agent_id)
        if department_id is not None:
            agent_subq = select(Agent.id).where(
                Agent.department_id == department_id, Agent.organization_id == self.org_id
            ).subquery()
            query = query.where(PerformanceMetric.agent_id.in_(select(agent_subq)))
            count_base = count_base.where(PerformanceMetric.agent_id.in_(select(agent_subq)))
        if period is not None:
            query = query.where(PerformanceMetric.period == period)
            count_base = count_base.where(PerformanceMetric.period == period)
        if date_from is not None:
            query = query.where(PerformanceMetric.period_start >= date_from)
            count_base = count_base.where(PerformanceMetric.period_start >= date_from)
        if date_to is not None:
            query = query.where(PerformanceMetric.period_end <= date_to)
            count_base = count_base.where(PerformanceMetric.period_end <= date_to)

        total = (await self.db.execute(count_base)).scalar_one()

        result = await self.db.execute(
            query.order_by(PerformanceMetric.period_start.desc())
            .offset(pagination.offset)
            .limit(pagination.size)
        )
        return list(result.scalars().all()), total

    async def get_total_agents(self) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Agent).where(Agent.organization_id == self.org_id)
        )
        return result.scalar_one()

    async def get_active_agents(self) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(Agent)
            .where(
                Agent.organization_id == self.org_id,
                Agent.status.in_([AgentStatus.ACTIVE, AgentStatus.BUSY]),
            )
        )
        return result.scalar_one()

    async def get_tasks_completed_since(self, since: datetime) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.organization_id == self.org_id,
                Task.status == TaskStatus.COMPLETED,
                Task.completed_at >= since,
            )
        )
        return result.scalar_one()

    async def get_daily_metrics_since(
        self, since: datetime
    ) -> list[PerformanceMetric]:
        result = await self.db.execute(
            self._scoped().where(
                PerformanceMetric.period == MetricPeriod.DAILY,
                PerformanceMetric.period_start >= since,
            )
        )
        return list(result.scalars().all())

    async def get_leaderboard(self, limit: int) -> list[PerformanceMetric]:
        result = await self.db.execute(
            self._scoped()
            .where(
                PerformanceMetric.period == MetricPeriod.DAILY,
                PerformanceMetric.success_rate.isnot(None),
            )
            .order_by(PerformanceMetric.success_rate.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_agent_trend(
        self,
        agent_id: uuid.UUID,
        period: MetricPeriod,
        limit: int,
    ) -> list[PerformanceMetric]:
        result = await self.db.execute(
            self._scoped()
            .where(
                PerformanceMetric.agent_id == agent_id,
                PerformanceMetric.period == period,
            )
            .order_by(PerformanceMetric.period_start.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_summary(self) -> dict:
        result = await self.db.execute(
            select(
                func.sum(PerformanceMetric.tasks_completed).label("total_completed"),
                func.sum(PerformanceMetric.tasks_failed).label("total_failed"),
                func.avg(PerformanceMetric.success_rate).label("avg_success_rate"),
                func.avg(PerformanceMetric.avg_response_ms).label("avg_response_ms"),
                func.sum(PerformanceMetric.cost_usd).label("total_cost"),
                func.sum(PerformanceMetric.token_usage).label("total_tokens"),
                func.count(func.distinct(PerformanceMetric.agent_id)).label("agents_measured"),
            ).where(
                PerformanceMetric.organization_id == self.org_id,
                PerformanceMetric.period == MetricPeriod.DAILY,
            )
        )
        return result.one()._asdict()

    async def get_daily_tasks_aggregated(self, days: int = 90) -> list[dict]:
        """Get daily completed/failed aggregated across all agents in this org."""
        result = await self.db.execute(
            select(
                cast(PerformanceMetric.period_start, String).label("date"),
                func.sum(PerformanceMetric.tasks_completed).label("completed"),
                func.sum(PerformanceMetric.tasks_failed).label("failed"),
            )
            .where(
                PerformanceMetric.organization_id == self.org_id,
                PerformanceMetric.period == MetricPeriod.DAILY,
            )
            .group_by(PerformanceMetric.period_start)
            .order_by(PerformanceMetric.period_start)
            .limit(days)
        )
        return [row._asdict() for row in result.all()]

    async def get_top_agents(self, limit: int = 10) -> list[dict]:
        """Get top agents by total tasks completed in this org."""
        result = await self.db.execute(
            select(
                PerformanceMetric.agent_id,
                Agent.name.label("agent_name"),
                func.sum(PerformanceMetric.tasks_completed).label("tasks_completed"),
                func.avg(PerformanceMetric.success_rate).label("success_rate"),
                func.sum(PerformanceMetric.cost_usd).label("cost_usd"),
            )
            .join(Agent, Agent.id == PerformanceMetric.agent_id)
            .where(
                PerformanceMetric.organization_id == self.org_id,
                PerformanceMetric.period == MetricPeriod.DAILY,
            )
            .group_by(PerformanceMetric.agent_id, Agent.name)
            .order_by(func.sum(PerformanceMetric.tasks_completed).desc())
            .limit(limit)
        )
        return [row._asdict() for row in result.all()]

    async def get_tasks_by_status(self) -> dict[str, int]:
        result = await self.db.execute(
            select(Task.status, func.count())
            .select_from(Task)
            .where(Task.organization_id == self.org_id)
            .group_by(Task.status)
        )
        return {str(row[0].value): row[1] for row in result.all()}

    async def get_agents_by_status(self) -> dict[str, int]:
        result = await self.db.execute(
            select(Agent.status, func.count())
            .select_from(Agent)
            .where(Agent.organization_id == self.org_id)
            .group_by(Agent.status)
        )
        return {str(row[0].value): row[1] for row in result.all()}

    async def get_agent_metrics_range(
        self,
        agent_id: uuid.UUID,
        period: MetricPeriod,
        start_date: datetime,
        end_date: datetime,
    ) -> list[PerformanceMetric]:
        result = await self.db.execute(
            self._scoped()
            .where(
                PerformanceMetric.agent_id == agent_id,
                PerformanceMetric.period == period,
                PerformanceMetric.period_start >= start_date,
                PerformanceMetric.period_start <= end_date,
            )
            .order_by(PerformanceMetric.period_start)
        )
        return list(result.scalars().all())

    async def delete_agent_metrics_range(
        self,
        agent_id: uuid.UUID,
        period: MetricPeriod,
        start_date: datetime,
        end_date: datetime,
    ) -> int:
        from sqlalchemy import delete

        result = await self.db.execute(
            delete(PerformanceMetric).where(
                PerformanceMetric.organization_id == self.org_id,
                PerformanceMetric.agent_id == agent_id,
                PerformanceMetric.period == period,
                PerformanceMetric.period_start >= start_date,
                PerformanceMetric.period_start <= end_date,
            )
        )
        return result.rowcount
