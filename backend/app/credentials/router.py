"""
Credential API endpoints — CRUD for API keys and secrets.

All endpoints require authentication and are org-scoped.
Secret values are write-only — responses only contain masked previews.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_org_id
from app.core.pagination import PaginatedResponse, PaginationParams
from app.dependencies import get_db
from app.credentials.schemas import (
    CredentialCreate,
    CredentialResponse,
    CredentialUpdate,
)
from app.credentials.service import CredentialService

router = APIRouter()


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
) -> CredentialService:
    return CredentialService(db, org_id)


@router.post("/", response_model=CredentialResponse, status_code=201)
async def create_credential(
    data: CredentialCreate,
    service: CredentialService = Depends(_get_service),
):
    return await service.create_credential(data)


@router.get("/", response_model=PaginatedResponse)
async def list_credentials(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    service_name: str | None = None,
    agent_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    service: CredentialService = Depends(_get_service),
):
    items, total = await service.list_credentials(
        page=page, size=size,
        service_name=service_name,
        agent_id=agent_id,
        is_active=is_active,
    )
    return PaginatedResponse.create(items, total, PaginationParams(page=page, size=size))


@router.get("/agent/{agent_id}", response_model=list[CredentialResponse])
async def list_agent_credentials(
    agent_id: uuid.UUID,
    service: CredentialService = Depends(_get_service),
):
    """Get all credentials available to a specific agent (assigned + shared)."""
    return await service.list_agent_credentials(agent_id)


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(
    credential_id: uuid.UUID,
    service: CredentialService = Depends(_get_service),
):
    return await service.get_credential(credential_id)


@router.patch("/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: uuid.UUID,
    data: CredentialUpdate,
    service: CredentialService = Depends(_get_service),
):
    return await service.update_credential(credential_id, data)


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: uuid.UUID,
    service: CredentialService = Depends(_get_service),
):
    await service.delete_credential(credential_id)
