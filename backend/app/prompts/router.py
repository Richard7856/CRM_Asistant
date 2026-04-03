import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import PaginatedResponse, PaginationParams
from app.prompts.schemas import (
    PromptCompareResponse,
    PromptTemplateCreate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
    PromptVersionCreate,
    PromptVersionResponse,
)
from app.prompts.service import PromptService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> PromptService:
    return PromptService(db)


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------


@router.get("/templates", response_model=PaginatedResponse)
async def list_templates(
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    service: PromptService = Depends(_get_service),
):
    pagination = PaginationParams(page=page, size=size)
    return await service.list_templates(pagination, category=category, search=search)


@router.post("/templates", response_model=PromptTemplateResponse, status_code=201)
async def create_template(
    payload: PromptTemplateCreate,
    service: PromptService = Depends(_get_service),
):
    return await service.create_template(payload)


@router.get("/templates/{template_id}", response_model=PromptTemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    service: PromptService = Depends(_get_service),
):
    return await service.get_template(template_id)


@router.patch("/templates/{template_id}", response_model=PromptTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    payload: PromptTemplateUpdate,
    service: PromptService = Depends(_get_service),
):
    return await service.update_template(template_id, payload)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    service: PromptService = Depends(_get_service),
):
    await service.delete_template(template_id)


# ---------------------------------------------------------------------------
# Prompt Versions
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/versions", response_model=PaginatedResponse)
async def list_versions(
    agent_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    service: PromptService = Depends(_get_service),
):
    pagination = PaginationParams(page=page, size=size)
    return await service.list_versions(agent_id, pagination)


@router.post(
    "/agents/{agent_id}/versions",
    response_model=PromptVersionResponse,
    status_code=201,
)
async def create_version(
    agent_id: uuid.UUID,
    payload: PromptVersionCreate,
    service: PromptService = Depends(_get_service),
):
    return await service.create_version(agent_id, payload)


@router.post(
    "/agents/{agent_id}/versions/{version}/activate",
    response_model=PromptVersionResponse,
)
async def activate_version(
    agent_id: uuid.UUID,
    version: int,
    service: PromptService = Depends(_get_service),
):
    return await service.activate_version(agent_id, version)


@router.get(
    "/agents/{agent_id}/versions/compare",
    response_model=PromptCompareResponse,
)
async def compare_versions(
    agent_id: uuid.UUID,
    v1: int = Query(...),
    v2: int = Query(...),
    service: PromptService = Depends(_get_service),
):
    return await service.compare_versions(agent_id, v1, v2)


@router.post(
    "/agents/{agent_id}/apply-template/{template_id}",
    response_model=PromptVersionResponse,
    status_code=201,
)
async def apply_template(
    agent_id: uuid.UUID,
    template_id: uuid.UUID,
    service: PromptService = Depends(_get_service),
):
    return await service.apply_template(agent_id, template_id)
