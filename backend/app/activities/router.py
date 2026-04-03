import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.activities.models import LogLevel
from app.activities.schemas import ActivityCreate, ActivityResponse, ActivitySummary
from app.activities.service import ActivityService
from app.auth.dependencies import get_org_id
from app.core.database import get_db
from app.core.pagination import PaginatedResponse, PaginationParams

router = APIRouter()


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
) -> ActivityService:
    return ActivityService(db, org_id)


@router.get("/", response_model=PaginatedResponse)
async def list_activities(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    agent_id: uuid.UUID | None = Query(default=None),
    task_id: uuid.UUID | None = Query(default=None),
    level: LogLevel | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    service: ActivityService = Depends(_get_service),
):
    pagination = PaginationParams(page=page, size=size)
    items, total = await service.list_activities(
        pagination,
        agent_id=agent_id,
        task_id=task_id,
        level=level,
        date_from=date_from,
        date_to=date_to,
    )
    return PaginatedResponse.create(
        items=[i.model_dump() for i in items], total=total, params=pagination
    )


@router.post("/", response_model=ActivityResponse, status_code=201)
async def create_activity(
    data: ActivityCreate,
    service: ActivityService = Depends(_get_service),
):
    return await service.create_activity(data)


@router.get("/summary", response_model=list[ActivitySummary])
async def get_activity_summary(
    service: ActivityService = Depends(_get_service),
):
    return await service.get_summary()
