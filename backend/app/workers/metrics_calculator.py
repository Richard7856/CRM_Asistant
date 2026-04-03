"""
Metrics calculator worker.
Aggregates performance data from tasks, activities, and interactions
into the performance_metrics table on a schedule.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.activities.models import ActivityLog
from app.agents.models import Agent, AgentStatus
from app.core.database import async_session_factory
from app.core.events import Event, event_bus
from app.interactions.models import AgentInteraction
from app.metrics.models import MetricPeriod, PerformanceMetric
from app.tasks.models import Task, TaskStatus

logger = logging.getLogger(__name__)


async def calculate_agent_daily_metrics(
    agent_id: uuid.UUID,
    organization_id: uuid.UUID,
    date: datetime,
    db,
) -> dict:
    """Calculate one agent's metrics for a single day."""
    # Ensure naive datetime (DB uses TIMESTAMP WITHOUT TIME ZONE)
    day_start = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    day_end = day_start + timedelta(days=1)

    # Tasks completed / failed
    task_counts = await db.execute(
        select(
            Task.status,
            func.count().label("cnt"),
        )
        .where(
            Task.assigned_to == agent_id,
            Task.updated_at >= day_start,
            Task.updated_at < day_end,
            Task.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED]),
        )
        .group_by(Task.status)
    )
    task_map = {row.status: row.cnt for row in task_counts}
    tasks_completed = task_map.get(TaskStatus.COMPLETED, 0)
    tasks_failed = task_map.get(TaskStatus.FAILED, 0)
    total_resolved = tasks_completed + tasks_failed
    success_rate = (tasks_completed / total_resolved) if total_resolved > 0 else None

    # Average response time from interactions
    avg_latency_result = await db.execute(
        select(func.avg(AgentInteraction.latency_ms))
        .where(
            AgentInteraction.from_agent_id == agent_id,
            AgentInteraction.occurred_at >= day_start,
            AgentInteraction.occurred_at < day_end,
            AgentInteraction.latency_ms.isnot(None),
        )
    )
    avg_response_ms = avg_latency_result.scalar()

    # Activity count
    activity_count_result = await db.execute(
        select(func.count())
        .select_from(ActivityLog)
        .where(
            ActivityLog.agent_id == agent_id,
            ActivityLog.occurred_at >= day_start,
            ActivityLog.occurred_at < day_end,
        )
    )
    activity_count = activity_count_result.scalar_one()

    # Token usage and cost from activity details JSONB
    activities = await db.execute(
        select(ActivityLog.details)
        .where(
            ActivityLog.agent_id == agent_id,
            ActivityLog.occurred_at >= day_start,
            ActivityLog.occurred_at < day_end,
        )
    )
    token_usage = 0
    cost_usd = 0.0
    for (details,) in activities:
        if isinstance(details, dict):
            token_usage += details.get("token_usage", 0) or 0
            cost_usd += float(details.get("cost_usd", 0) or 0)

    # Also pull from interaction payloads
    interactions = await db.execute(
        select(AgentInteraction.payload)
        .where(
            AgentInteraction.from_agent_id == agent_id,
            AgentInteraction.occurred_at >= day_start,
            AgentInteraction.occurred_at < day_end,
        )
    )
    for (payload,) in interactions:
        if isinstance(payload, dict):
            token_usage += payload.get("token_usage", 0) or 0
            cost_usd += float(payload.get("cost_usd", 0) or 0)

    # Upsert into performance_metrics — organization_id is required (NOT NULL)
    values = {
        "agent_id": agent_id,
        "organization_id": organization_id,
        "period": MetricPeriod.DAILY,
        "period_start": day_start,
        "period_end": day_end,
        "tasks_completed": tasks_completed,
        "tasks_failed": tasks_failed,
        "success_rate": success_rate,
        "avg_response_ms": float(avg_response_ms) if avg_response_ms else None,
        "token_usage": token_usage,
        "cost_usd": cost_usd,
        "custom_kpis": {"activity_count": activity_count},
    }

    stmt = pg_insert(PerformanceMetric).values(**values, id=uuid.uuid4())
    stmt = stmt.on_conflict_do_update(
        constraint="uq_perf_agent_period",
        set_={
            "tasks_completed": stmt.excluded.tasks_completed,
            "tasks_failed": stmt.excluded.tasks_failed,
            "success_rate": stmt.excluded.success_rate,
            "avg_response_ms": stmt.excluded.avg_response_ms,
            "token_usage": stmt.excluded.token_usage,
            "cost_usd": stmt.excluded.cost_usd,
            "custom_kpis": stmt.excluded.custom_kpis,
        },
    )
    await db.execute(stmt)

    logger.debug("Calculated daily metrics for agent %s on %s", agent_id, date.date())
    return values


async def calculate_all_daily_metrics(db) -> int:
    """Calculate daily metrics for all active agents for yesterday."""
    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)

    # Fetch both agent id and organization_id — required for the NOT NULL constraint
    result = await db.execute(
        select(Agent.id, Agent.organization_id).where(
            Agent.status.not_in([AgentStatus.OFFLINE])
        )
    )
    agents = result.all()  # list of (agent_id, organization_id)

    count = 0
    for agent_id, organization_id in agents:
        try:
            await calculate_agent_daily_metrics(agent_id, organization_id, yesterday, db)
            count += 1
        except Exception:
            logger.exception("Failed to calculate metrics for agent %s", agent_id)

    await db.commit()
    logger.info("Calculated daily metrics for %d/%d agents", count, len(agents))

    # Broadcast to all SSE subscribers so dashboards refresh without polling
    await event_bus.publish(Event(
        type="metric.updated",
        data={
            "period": "daily",
            "agents_updated": count,
            "calculated_at": datetime.utcnow().isoformat(),
        },
    ))

    return count


async def _rollup_period(
    db,
    source_period: MetricPeriod,
    target_period: MetricPeriod,
    period_start: datetime,
    period_end: datetime,
):
    """Aggregate source period metrics into a target period metric."""
    # Include organization_id in GROUP BY — it's required NOT NULL on the target row
    result = await db.execute(
        select(
            PerformanceMetric.agent_id,
            PerformanceMetric.organization_id,
            func.sum(PerformanceMetric.tasks_completed).label("tasks_completed"),
            func.sum(PerformanceMetric.tasks_failed).label("tasks_failed"),
            func.avg(PerformanceMetric.avg_response_ms).label("avg_response_ms"),
            func.sum(PerformanceMetric.token_usage).label("token_usage"),
            func.sum(PerformanceMetric.cost_usd).label("cost_usd"),
        )
        .where(
            PerformanceMetric.period == source_period,
            PerformanceMetric.period_start >= period_start,
            PerformanceMetric.period_start < period_end,
        )
        .group_by(PerformanceMetric.agent_id, PerformanceMetric.organization_id)
    )
    rows = result.all()

    for row in rows:
        total = row.tasks_completed + row.tasks_failed
        success_rate = (row.tasks_completed / total) if total > 0 else None

        values = {
            "agent_id": row.agent_id,
            "organization_id": row.organization_id,
            "period": target_period,
            "period_start": period_start,
            "period_end": period_end,
            "tasks_completed": row.tasks_completed,
            "tasks_failed": row.tasks_failed,
            "success_rate": success_rate,
            "avg_response_ms": float(row.avg_response_ms) if row.avg_response_ms else None,
            "token_usage": row.token_usage or 0,
            "cost_usd": float(row.cost_usd or 0),
            "custom_kpis": {},
        }

        stmt = pg_insert(PerformanceMetric).values(**values, id=uuid.uuid4())
        stmt = stmt.on_conflict_do_update(
            constraint="uq_perf_agent_period",
            set_={
                "tasks_completed": stmt.excluded.tasks_completed,
                "tasks_failed": stmt.excluded.tasks_failed,
                "success_rate": stmt.excluded.success_rate,
                "avg_response_ms": stmt.excluded.avg_response_ms,
                "token_usage": stmt.excluded.token_usage,
                "cost_usd": stmt.excluded.cost_usd,
                "custom_kpis": stmt.excluded.custom_kpis,
            },
        )
        await db.execute(stmt)

    logger.info(
        "Rolled up %s metrics for %d agents (%s to %s)",
        target_period.value, len(rows), period_start.date(), period_end.date(),
    )


async def rollup_weekly_metrics(db):
    """Aggregate daily metrics into weekly (last full week, Mon-Sun)."""
    now = datetime.utcnow()
    # Last Monday
    last_monday = (now - timedelta(days=now.weekday() + 7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = last_monday + timedelta(days=7)

    await _rollup_period(db, MetricPeriod.DAILY, MetricPeriod.WEEKLY, last_monday, week_end)
    await db.commit()


async def rollup_monthly_metrics(db):
    """Aggregate daily metrics into monthly (last full month)."""
    now = datetime.utcnow()
    first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = first_of_this_month
    last_month_start = (first_of_this_month - timedelta(days=1)).replace(day=1)

    await _rollup_period(db, MetricPeriod.DAILY, MetricPeriod.MONTHLY, last_month_start, last_month_end)
    await db.commit()


async def run_metrics_calculator(interval_seconds: int = 3600):
    """Main loop: calculate metrics on a schedule."""
    logger.info("Starting metrics calculator (interval=%ds)", interval_seconds)
    while True:
        try:
            async with async_session_factory() as session:
                await calculate_all_daily_metrics(session)

                # Weekly rollup on Mondays
                now = datetime.utcnow()
                if now.weekday() == 0:
                    await rollup_weekly_metrics(session)

                # Monthly rollup on the 1st
                if now.day == 1:
                    await rollup_monthly_metrics(session)

        except Exception:
            logger.exception("Metrics calculator error")

        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_metrics_calculator())
