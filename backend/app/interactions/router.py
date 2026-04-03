import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import PaginatedResponse, PaginationParams
from app.interactions.models import InteractionChannel
from app.interactions.schemas import GraphData, InteractionCreate, InteractionResponse
from app.auth.dependencies import get_org_id
from app.interactions.service import InteractionService

router = APIRouter()


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
) -> InteractionService:
    return InteractionService(db, org_id)


@router.get("/", response_model=PaginatedResponse)
async def list_interactions(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    agent_id: uuid.UUID | None = Query(default=None),
    channel: InteractionChannel | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    service: InteractionService = Depends(_get_service),
):
    pagination = PaginationParams(page=page, size=size)
    items, total = await service.list_interactions(
        pagination,
        agent_id=agent_id,
        channel=channel,
        date_from=date_from,
        date_to=date_to,
    )
    return PaginatedResponse.create(
        items=[i.model_dump() for i in items], total=total, params=pagination
    )


@router.post("/", response_model=InteractionResponse, status_code=201)
async def create_interaction(
    data: InteractionCreate,
    service: InteractionService = Depends(_get_service),
):
    return await service.create_interaction(data)


@router.get("/graph", response_model=GraphData)
async def get_interaction_graph(
    service: InteractionService = Depends(_get_service),
):
    return await service.get_graph()
