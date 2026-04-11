"""
Seed script — 30 days of realistic daily metrics for all DigitalMind agents.

Each agent has a unique performance profile that reflects its role:
supervisors handle fewer tasks but with high success rate,
operational agents handle more tasks with role-appropriate characteristics.

Run: python seed_metrics.py
Re-run safe: uses ON CONFLICT to upsert existing records.
"""

import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.agents.models import Agent
from app.auth.models import Organization  # noqa: F401 — needed for Agent relationship resolution
from app.core.database import async_session_factory
from app.metrics.models import MetricPeriod, PerformanceMetric

# Import all models so relationships resolve
from app.tasks.models import Task  # noqa: F401
from app.activities.models import ActivityLog  # noqa: F401
from app.interactions.models import AgentInteraction  # noqa: F401
from app.improvements.models import ImprovementPoint  # noqa: F401
from app.departments.models import Department  # noqa: F401


# Per-agent performance profiles that tell a story in the dashboard.
# (base_success_rate, base_tasks_per_day, base_latency_ms, base_tokens, base_cost_usd)
AGENT_PROFILES = {
    # Supervisors: fewer tasks (they coordinate), high success, moderate cost
    "director-contenido": (0.95, 6, 1200, 60000, 1.80),
    "account-manager":    (0.93, 8, 900, 45000, 1.40),
    "strategist":         (0.96, 5, 1500, 70000, 2.10),
    # Operational agents: more tasks, varied performance
    "copywriter":         (0.91, 18, 800, 55000, 1.50),   # high volume, good quality
    "investigador":       (0.88, 12, 1100, 80000, 2.00),   # slower (research), more tokens
    "analista-propuestas":(0.90, 10, 1400, 65000, 1.80),   # moderate, detailed output
    "soporte-tecnico":    (0.85, 20, 600, 30000, 0.80),    # high volume, lower success (external)
    "data-analyst":       (0.94, 14, 700, 90000, 2.20),    # fast, heavy on tokens (data crunching)
}

DAYS_BACK = 30


def _jitter(base: float, pct: float = 0.15) -> float:
    """Add random variance to a base value."""
    return base * (1 + random.uniform(-pct, pct))


def _trend(day_index: int, days_total: int, strength: float = 0.05) -> float:
    """Slight upward trend over time — agents improve with use."""
    return 1 + (day_index / days_total) * strength


async def seed_metrics():
    async with async_session_factory() as session:
        # Get org_id
        org_result = await session.execute(select(Organization.id).limit(1))
        org_row = org_result.first()
        if org_row is None:
            print("ERROR: No organization found. Run seed.py first.")
            return
        org_id = org_row[0]

        # Get all agents
        result = await session.execute(select(Agent.id, Agent.name, Agent.slug))
        agents = result.all()

        if not agents:
            print("No agents found. Run seed.py first.")
            return

        print(f"Generating {DAYS_BACK} days of metrics for {len(agents)} agents...")

        # DB columns are TIMESTAMP WITHOUT TIME ZONE — use naive datetimes
        now = datetime.utcnow()  # noqa: DTZ003
        records_created = 0

        for agent_id, agent_name, agent_slug in agents:
            # Use agent-specific profile, fall back to sensible defaults
            profile = AGENT_PROFILES.get(agent_slug)
            if profile:
                base_success, base_tasks, base_latency, base_tokens, base_cost = profile
            else:
                base_success, base_tasks, base_latency, base_tokens, base_cost = (0.90, 12, 900, 50000, 1.20)

            for day_offset in range(DAYS_BACK, 0, -1):
                date = now - timedelta(days=day_offset)
                day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                day_index = DAYS_BACK - day_offset

                trend = _trend(day_index, DAYS_BACK)

                tasks_total = max(1, int(_jitter(base_tasks * trend, 0.3)))
                success_rate = min(0.9999, max(0.60, _jitter(base_success * trend, 0.08)))
                tasks_completed = max(0, int(tasks_total * success_rate))
                tasks_failed = tasks_total - tasks_completed

                actual_sr = tasks_completed / tasks_total if tasks_total > 0 else None

                avg_response_ms = max(50, _jitter(base_latency / trend, 0.2))
                token_usage = max(0, int(_jitter(base_tokens * trend, 0.25)))
                cost_usd = max(0, round(_jitter(base_cost * trend, 0.2), 4))
                activity_count = max(0, int(_jitter(tasks_total * 3, 0.3)))

                # ~5% chance of a bad day (simulate incidents)
                if random.random() < 0.05:
                    tasks_failed += random.randint(3, 8)
                    actual_sr = tasks_completed / (tasks_completed + tasks_failed) if (tasks_completed + tasks_failed) > 0 else None
                    avg_response_ms *= random.uniform(1.5, 3.0)

                values = {
                    "id": uuid.uuid4(),
                    "agent_id": agent_id,
                    "organization_id": org_id,
                    "period": MetricPeriod.DAILY,
                    "period_start": day_start,
                    "period_end": day_end,
                    "tasks_completed": tasks_completed,
                    "tasks_failed": tasks_failed,
                    "success_rate": round(actual_sr, 4) if actual_sr is not None else None,
                    "avg_response_ms": round(avg_response_ms, 2),
                    "token_usage": token_usage,
                    "cost_usd": cost_usd,
                    "custom_kpis": {"activity_count": activity_count},
                }

                stmt = pg_insert(PerformanceMetric).values(**values)
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
                    }
                )
                await session.execute(stmt)
                records_created += 1

            print(f"  {agent_name} ({agent_slug}): {DAYS_BACK} daily records")

        # Generate weekly rollups from daily data
        print("Generating weekly rollups...")
        for week_offset in range(4):
            week_end_day = now - timedelta(days=now.weekday() + 7 * week_offset)
            week_start = (week_end_day - timedelta(days=7)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            week_end = week_start + timedelta(days=7)

            for agent_id, agent_name, _ in agents:
                daily_result = await session.execute(
                    select(PerformanceMetric).where(
                        PerformanceMetric.agent_id == agent_id,
                        PerformanceMetric.period == MetricPeriod.DAILY,
                        PerformanceMetric.period_start >= week_start,
                        PerformanceMetric.period_start < week_end,
                    )
                )
                daily_rows = daily_result.scalars().all()
                if not daily_rows:
                    continue

                total_completed = sum(r.tasks_completed for r in daily_rows)
                total_failed = sum(r.tasks_failed for r in daily_rows)
                total = total_completed + total_failed
                sr = total_completed / total if total > 0 else None
                latencies = [float(r.avg_response_ms) for r in daily_rows if r.avg_response_ms]
                avg_lat = sum(latencies) / len(latencies) if latencies else None

                values = {
                    "id": uuid.uuid4(),
                    "agent_id": agent_id,
                    "organization_id": org_id,
                    "period": MetricPeriod.WEEKLY,
                    "period_start": week_start,
                    "period_end": week_end,
                    "tasks_completed": total_completed,
                    "tasks_failed": total_failed,
                    "success_rate": round(sr, 4) if sr else None,
                    "avg_response_ms": round(avg_lat, 2) if avg_lat else None,
                    "token_usage": sum(r.token_usage for r in daily_rows),
                    "cost_usd": round(sum(float(r.cost_usd) for r in daily_rows), 4),
                    "custom_kpis": {},
                }

                stmt = pg_insert(PerformanceMetric).values(**values)
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
                    }
                )
                await session.execute(stmt)
                records_created += 1

        await session.commit()
        print(f"\nDone! Created/updated {records_created} metric records.")


if __name__ == "__main__":
    asyncio.run(seed_metrics())
