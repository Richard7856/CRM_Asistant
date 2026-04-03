import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import PaginatedResponse, PaginationParams
from app.improvements.models import ImprovementStatus
from app.improvements.schemas import ImprovementCreate, ImprovementResponse, ImprovementUpdate
from app.auth.dependencies import get_org_id
from app.improvements.service import ImprovementService
from app.tasks.models import TaskPriority

router = APIRouter()


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
) -> ImprovementService:
    return ImprovementService(db, org_id)


@router.get("/", response_model=PaginatedResponse)
async def list_improvements(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    agent_id: uuid.UUID | None = Query(default=None),
    status: ImprovementStatus | None = Query(default=None),
    category: str | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    service: ImprovementService = Depends(_get_service),
):
    pagination = PaginationParams(page=page, size=size)
    items, total = await service.list_improvements(
        pagination,
        agent_id=agent_id,
        status=status,
        category=category,
        priority=priority,
    )
    return PaginatedResponse.create(
        items=[i.model_dump() for i in items], total=total, params=pagination
    )


@router.post("/", response_model=ImprovementResponse, status_code=201)
async def create_improvement(
    data: ImprovementCreate,
    service: ImprovementService = Depends(_get_service),
):
    return await service.create_improvement(data)


@router.patch("/{improvement_id}", response_model=ImprovementResponse)
async def update_improvement(
    improvement_id: uuid.UUID,
    data: ImprovementUpdate,
    service: ImprovementService = Depends(_get_service),
):
    return await service.update_improvement(improvement_id, data)
