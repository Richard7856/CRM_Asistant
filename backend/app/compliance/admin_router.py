"""
Compliance admin API (P0.7 — LFPDPPP).

Mounted under /api/v1/admin → routes here live at /api/v1/admin/compliance/...

Authorization:
- OWNER only for anything destructive (erase) or for the full tenant export.
- OWNER + ADMIN for the classification registry and per-user export.

Note on erase-tenant: it always targets the CALLER's own organization (org_id
from the JWT). You cannot erase another tenant. The request body must echo the
org slug as a confirmation. After it runs, the org — including the caller's user
— is gone, so the returned certificate is the only durable record; capture it.
"""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_org_id, require_role
from app.auth.models import User, UserRole
from app.compliance.schemas import (
    DataClassificationResponse,
    EraseTenantRequest,
    ErasureCertificateResponse,
    RetentionEligibleResponse,
    RetentionPolicyResponse,
    RetentionPolicyUpsert,
)
from app.compliance.service import ComplianceService, RetentionService
from app.core.database import get_db

router = APIRouter()

_owner_only = Depends(require_role(UserRole.OWNER))
_owner_or_admin = Depends(require_role(UserRole.OWNER, UserRole.ADMIN))


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
    user: User = Depends(get_current_user),
) -> ComplianceService:
    return ComplianceService(db, org_id, actor_user_id=user.id)


def _get_retention_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
    user: User = Depends(get_current_user),
) -> RetentionService:
    return RetentionService(db, org_id, actor_user_id=user.id)


@router.get(
    "/compliance/classification",
    response_model=DataClassificationResponse,
    dependencies=[_owner_or_admin],
)
async def get_classification(service: ComplianceService = Depends(_get_service)):
    """What data we hold and how it's classified (PII / operacional / metadata)."""
    return DataClassificationResponse(tables=service.get_classification())


@router.get("/compliance/export", dependencies=[_owner_only])
async def export_tenant(service: ComplianceService = Depends(_get_service)) -> JSONResponse:
    """Full export of the caller's organization data as a downloadable JSON file."""
    bundle = await service.export_tenant()
    return JSONResponse(
        content=bundle,
        headers={
            "Content-Disposition": 'attachment; filename="tenant_export.json"'
        },
    )


@router.get("/compliance/export/users/{user_id}", dependencies=[_owner_or_admin])
async def export_user(
    user_id: uuid.UUID,
    service: ComplianceService = Depends(_get_service),
) -> JSONResponse:
    """Export a single user's identifiable data (right of access)."""
    bundle = await service.export_user(user_id)
    return JSONResponse(
        content=bundle,
        headers={
            "Content-Disposition": f'attachment; filename="user_{user_id}_export.json"'
        },
    )


@router.delete(
    "/compliance/erase-tenant",
    response_model=ErasureCertificateResponse,
    dependencies=[_owner_only],
)
async def erase_tenant(
    body: EraseTenantRequest,
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
    user: User = Depends(get_current_user),
):
    """
    Irreversibly erase the caller's own organization and all its data. Requires
    `confirmation` to equal the org slug. Returns the erasure certificate — the
    only record that survives the deletion.
    """
    service = ComplianceService(db, org_id, actor_user_id=user.id)
    certificate = await service.erase_tenant(body.confirmation, requester=user)
    return ErasureCertificateResponse.model_validate(certificate)


@router.delete(
    "/compliance/erase-users/{user_id}",
    response_model=ErasureCertificateResponse,
    dependencies=[_owner_only],
)
async def erase_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
    user: User = Depends(get_current_user),
):
    """Anonymize a single user in place (right to be forgotten). Returns a certificate."""
    service = ComplianceService(db, org_id, actor_user_id=user.id)
    certificate = await service.erase_user(user_id, requester=user)
    return ErasureCertificateResponse.model_validate(certificate)


# ─── Retention (P0.7b) ────────────────────────────────────────────────────────


@router.get(
    "/compliance/retention/eligible",
    response_model=RetentionEligibleResponse,
    dependencies=[_owner_or_admin],
)
async def get_retention_eligible(service: RetentionService = Depends(_get_retention_service)):
    """Which tables can have a retention policy + recommended windows."""
    return RetentionEligibleResponse(eligible=service.get_eligible())


@router.get(
    "/compliance/retention/policies",
    response_model=list[RetentionPolicyResponse],
    dependencies=[_owner_or_admin],
)
async def list_retention_policies(service: RetentionService = Depends(_get_retention_service)):
    policies = await service.list_policies()
    return [RetentionPolicyResponse.model_validate(p) for p in policies]


@router.put(
    "/compliance/retention/policies",
    response_model=RetentionPolicyResponse,
    dependencies=[_owner_only],
)
async def upsert_retention_policy(
    body: RetentionPolicyUpsert,
    service: RetentionService = Depends(_get_retention_service),
):
    """Create or update the retention policy for one eligible table."""
    policy = await service.upsert_policy(
        table_name=body.table_name,
        retention_days=body.retention_days,
        is_enabled=body.is_enabled,
    )
    return RetentionPolicyResponse.model_validate(policy)


@router.delete(
    "/compliance/retention/policies/{policy_id}",
    status_code=204,
    dependencies=[_owner_only],
)
async def delete_retention_policy(
    policy_id: uuid.UUID,
    service: RetentionService = Depends(_get_retention_service),
):
    await service.delete_policy(policy_id)
