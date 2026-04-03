import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import PaginatedResponse, PaginationParams
from app.metrics.models import MetricPeriod
from app.metrics.schemas import LeaderboardEntry, MetricOverview, MetricSummary, TrendResponse
from app.auth.dependencies import get_org_id
from app.metrics.service import MetricService

router = APIRouter()


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
) -> MetricService:
    return MetricService(db, org_id)


@router.get("/", response_model=PaginatedResponse)
async def list_metrics(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    agent_id: uuid.UUID | None = Query(default=None),
    department_id: uuid.UUID | None = Query(default=None),
    period: MetricPeriod | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    service: MetricService = Depends(_get_service),
):
    pagination = PaginationParams(page=page, size=size)
    items, total = await service.list_metrics(
        pagination,
        agent_id=agent_id,
        department_id=department_id,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    return PaginatedResponse.create(
        items=[i.model_dump() for i in items], total=total, params=pagination
    )


@router.get("/overview", response_model=MetricOverview)
async def get_overview(
    service: MetricService = Depends(_get_service),
):
    return await service.get_overview()


@router.get("/summary", response_model=MetricSummary)
async def get_summary(
    service: MetricService = Depends(_get_service),
):
    """Global summary stats across all agents and all time."""
    return await service.get_summary()


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    top_n: int = Query(default=10, ge=1, le=100),
    service: MetricService = Depends(_get_service),
):
    return await service.get_leaderboard(top_n)


@router.get("/agents/{agent_id}/trend", response_model=TrendResponse)
async def get_agent_trend(
    agent_id: uuid.UUID,
    period: MetricPeriod = Query(default=MetricPeriod.DAILY),
    limit: int = Query(default=30, ge=1, le=365),
    service: MetricService = Depends(_get_service),
):
    """Get trend data for a specific agent (for charts)."""
    return await service.get_agent_trend(agent_id, period, limit)


@router.post("/recalculate/{agent_id}")
async def recalculate_agent_metrics(
    agent_id: uuid.UUID,
    days: int = Query(default=30, ge=1, le=365, description="Number of days to recalculate"),
    service: MetricService = Depends(_get_service),
):
    """Trigger recalculation of metrics for a specific agent."""
    now = datetime.utcnow()
    start_date = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    count = await service.recalculate_agent_metrics(agent_id, start_date, end_date)
    return {"status": "ok", "agent_id": str(agent_id), "days_recalculated": count}
