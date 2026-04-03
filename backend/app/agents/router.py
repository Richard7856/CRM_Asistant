import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import AgentOrigin, AgentStatus
from app.agents.schemas import (
    AgentCreateInternal,
    AgentDetailResponse,
    AgentRegisterExternal,
    AgentResponse,
    AgentUpdate,
    ApiKeyOut,
    RoleCreate,
    RoleResponse,
)
from app.agents.service import AgentService
from app.auth.dependencies import get_org_id
from app.core.database import get_db
from app.core.pagination import PaginatedResponse, PaginationParams

router = APIRouter()


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
) -> AgentService:
    return AgentService(db, org_id)


# ---------------------------------------------------------------------------
# Roles  (literal paths registered before parameterised /{agent_id} routes)
# ---------------------------------------------------------------------------


@router.get("/roles/", response_model=list[RoleResponse])
async def list_roles(service: AgentService = Depends(_get_service)):
    return await service.list_roles()


@router.post("/roles/", response_model=RoleResponse, status_code=201)
async def create_role(
    payload: RoleCreate,
    service: AgentService = Depends(_get_service),
):
    return await service.create_role(payload)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


@router.get("/", response_model=PaginatedResponse)
async def list_agents(
    department_id: uuid.UUID | None = Query(default=None),
    status: AgentStatus | None = Query(default=None),
    origin: AgentOrigin | None = Query(default=None),
    role_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    service: AgentService = Depends(_get_service),
):
    pagination = PaginationParams(page=page, size=size)
    return await service.list_agents(
        pagination,
        department_id=department_id,
        status=status,
        origin=origin,
        role_id=role_id,
    )


@router.post("/", response_model=AgentDetailResponse, status_code=201)
async def create_internal_agent(
    payload: AgentCreateInternal,
    service: AgentService = Depends(_get_service),
):
    return await service.create_internal_agent(payload)


@router.post("/register", status_code=201)
async def register_external_agent(
    payload: AgentRegisterExternal,
    service: AgentService = Depends(_get_service),
):
    agent_detail, api_key = await service.register_external_agent(payload)
    return {"agent": agent_detail, "api_key": api_key}


@router.get("/{agent_id}", response_model=AgentDetailResponse)
async def get_agent(
    agent_id: uuid.UUID,
    service: AgentService = Depends(_get_service),
):
    return await service.get_agent(agent_id)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    service: AgentService = Depends(_get_service),
):
    return await service.update_agent(agent_id, payload)


@router.delete("/{agent_id}", response_model=AgentResponse)
async def deactivate_agent(
    agent_id: uuid.UUID,
    service: AgentService = Depends(_get_service),
):
    return await service.deactivate_agent(agent_id)


@router.get("/{agent_id}/subordinates", response_model=list[AgentResponse])
async def get_subordinates(
    agent_id: uuid.UUID,
    service: AgentService = Depends(_get_service),
):
    return await service.get_subordinates(agent_id)


@router.post("/{agent_id}/heartbeat", response_model=AgentResponse)
async def record_heartbeat(
    agent_id: uuid.UUID,
    service: AgentService = Depends(_get_service),
):
    return await service.record_heartbeat(agent_id)
