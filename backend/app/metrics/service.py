import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.metrics.models import MetricPeriod
from app.metrics.repository import MetricRepository
from app.metrics.schemas import (
    DailyTaskPoint,
    LeaderboardEntry,
    MetricOverview,
    MetricResponse,
    MetricSummary,
    TopAgentEntry,
    TrendPoint,
    TrendResponse,
)


class MetricService:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id
        self.repo = MetricRepository(db, org_id)

    async def list_metrics(
        self,
        pagination: PaginationParams,
        *,
        agent_id: uuid.UUID | None = None,
        department_id: uuid.UUID | None = None,
        period: MetricPeriod | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> tuple[list[MetricResponse], int]:
        metrics, total = await self.repo.list_all(
            pagination,
            agent_id=agent_id,
            department_id=department_id,
            period=period,
            date_from=date_from,
            date_to=date_to,
        )
        return [MetricResponse.model_validate(m) for m in metrics], total

    async def get_overview(self) -> MetricOverview:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        total_agents = await self.repo.get_total_agents()
        active_agents = await self.repo.get_active_agents()
        tasks_completed_today = await self.repo.get_tasks_completed_since(today_start)
        daily_metrics = await self.repo.get_daily_metrics_since(today_start)

        if daily_metrics:
            rates = [m.success_rate for m in daily_metrics if m.success_rate is not None]
            response_times = [m.avg_response_ms for m in daily_metrics if m.avg_response_ms is not None]
            costs = [float(m.cost_usd) for m in daily_metrics]
            overall_success_rate = sum(rates) / len(rates) if rates else None
            avg_response_ms = sum(response_times) / len(response_times) if response_times else None
            total_cost_today = sum(costs)
        else:
            overall_success_rate = None
            avg_response_ms = None
            total_cost_today = 0.0

        return MetricOverview(
            total_agents=total_agents,
            active_agents=active_agents,
            tasks_completed_today=tasks_completed_today,
            overall_success_rate=float(overall_success_rate) if overall_success_rate else None,
            avg_response_ms=float(avg_response_ms) if avg_response_ms else None,
            total_cost_today=total_cost_today,
        )

    async def get_leaderboard(self, top_n: int = 10) -> list[LeaderboardEntry]:
        metrics = await self.repo.get_leaderboard(top_n)
        return [
            LeaderboardEntry(
                agent_id=m.agent_id,
                success_rate=float(m.success_rate) if m.success_rate else 0.0,
                tasks_completed=m.tasks_completed,
            )
            for m in metrics
        ]

    async def get_agent_trend(
        self,
        agent_id: uuid.UUID,
        period: MetricPeriod = MetricPeriod.DAILY,
        limit: int = 30,
    ) -> TrendResponse:
        metrics = await self.repo.get_agent_trend(agent_id, period, limit)
        data = [
            TrendPoint(
                period_start=m.period_start,
                period_end=m.period_end,
                tasks_completed=m.tasks_completed,
                tasks_failed=m.tasks_failed,
                success_rate=float(m.success_rate) if m.success_rate is not None else None,
                avg_response_ms=float(m.avg_response_ms) if m.avg_response_ms is not None else None,
                token_usage=m.token_usage,
                cost_usd=float(m.cost_usd),
            )
            for m in metrics
        ]
        # Return in chronological order
        data.reverse()
        return TrendResponse(agent_id=agent_id, period=period, data=data)

    async def get_summary(self) -> MetricSummary:
        row = await self.repo.get_summary()
        daily_raw = await self.repo.get_daily_tasks_aggregated(90)
        top_raw = await self.repo.get_top_agents(10)
        tasks_by_status = await self.repo.get_tasks_by_status()
        agents_by_status = await self.repo.get_agents_by_status()

        daily_tasks = [
            DailyTaskPoint(
                date=d["date"][:10],
                completed=int(d["completed"] or 0),
                failed=int(d["failed"] or 0),
            )
            for d in daily_raw
        ]

        top_agents = [
            TopAgentEntry(
                agent_id=a["agent_id"],
                agent_name=a["agent_name"] or "Unknown",
                tasks_completed=int(a["tasks_completed"] or 0),
                success_rate=float(a["success_rate"]) if a.get("success_rate") else 0.0,
                cost_usd=float(a["cost_usd"] or 0),
            )
            for a in top_raw
        ]

        return MetricSummary(
            total_tasks_completed=row.get("total_completed") or 0,
            total_tasks_failed=row.get("total_failed") or 0,
            avg_success_rate=float(row["avg_success_rate"]) if row.get("avg_success_rate") else None,
            avg_response_ms=float(row["avg_response_ms"]) if row.get("avg_response_ms") else None,
            total_cost_usd=float(row.get("total_cost") or 0),
            total_token_usage=row.get("total_tokens") or 0,
            agents_measured=row.get("agents_measured") or 0,
            daily_tasks=daily_tasks,
            top_agents=top_agents,
            tasks_by_status=tasks_by_status,
            agents_by_status=agents_by_status,
        )

    async def recalculate_agent_metrics(
        self,
        agent_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> int:
        """Recalculate daily metrics for an agent over a date range."""
        from app.workers.metrics_calculator import calculate_agent_daily_metrics

        # Delete existing daily metrics in range
        await self.repo.delete_agent_metrics_range(
            agent_id, MetricPeriod.DAILY, start_date, end_date
        )

        current = start_date
        count = 0
        while current <= end_date:
            await calculate_agent_daily_metrics(agent_id, current, self.db)
            current += timedelta(days=1)
            count += 1

        await self.db.commit()
        return count
