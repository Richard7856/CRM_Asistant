"""
Admin endpoints to configure AutonomyPolicy rows.

Only OWNER/ADMIN can touch policies. Each change is audit-logged via
AUTONOMY_POLICY_CHANGED. The preview endpoint lets a UI show "what level
would apply if I tried this combo right now" without executing anything.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.schemas import (
    AutonomyPolicyCreate,
    AutonomyPolicyResponse,
    AutonomyPolicyUpdate,
    PolicyPreviewRequest,
    PolicyPreviewResponse,
)
from app.approvals.service import PolicyService
from app.auth.dependencies import get_current_user, get_org_id, require_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.core.exceptions import NotFoundError

router = APIRouter()

_admin_only = Depends(require_role(UserRole.OWNER, UserRole.ADMIN))


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
    user: User = Depends(get_current_user),
) -> PolicyService:
    return PolicyService(db, org_id, actor_user_id=user.id)


@router.get(
    "/autonomy-policies",
    response_model=list[AutonomyPolicyResponse],
    dependencies=[_admin_only],
)
async def list_policies(service: PolicyService = Depends(_get_service)):
    """List ALL policies for the current org."""
    policies = await service.list_policies()
    return [AutonomyPolicyResponse.model_validate(p) for p in policies]


@router.post(
    "/autonomy-policies",
    response_model=AutonomyPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_admin_only],
)
async def create_policy(
    body: AutonomyPolicyCreate,
    service: PolicyService = Depends(_get_service),
):
    """Create a new policy. Idempotency is NOT enforced — admin can create
    overlapping policies; the resolver picks the most specific."""
    policy = await service.create_policy(
        scope_key=body.scope_key,
        action_pattern=body.action_pattern,
        autonomy_level=body.autonomy_level,
        auto_promote_threshold=body.auto_promote_threshold,
    )
    return AutonomyPolicyResponse.model_validate(policy)


@router.put(
    "/autonomy-policies/{policy_id}",
    response_model=AutonomyPolicyResponse,
    dependencies=[_admin_only],
)
async def update_policy(
    policy_id: uuid.UUID,
    body: AutonomyPolicyUpdate,
    service: PolicyService = Depends(_get_service),
):
    try:
        policy = await service.update_policy(
            policy_id,
            autonomy_level=body.autonomy_level,
            auto_promote_threshold=body.auto_promote_threshold,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return AutonomyPolicyResponse.model_validate(policy)


@router.delete(
    "/autonomy-policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_admin_only],
)
async def delete_policy(
    policy_id: uuid.UUID,
    service: PolicyService = Depends(_get_service),
):
    try:
        await service.delete_policy(policy_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/autonomy-policies/preview",
    response_model=PolicyPreviewResponse,
    dependencies=[_admin_only],
)
async def preview_policy(
    body: PolicyPreviewRequest,
    service: PolicyService = Depends(_get_service),
):
    """
    "If this agent tried this action right now, what level would apply?"
    Lets admins sanity-check policies without actually triggering anything.
    """
    try:
        level, policy, matched_scope, matched_pattern = await service.preview_level(
            body.agent_id, body.action
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return PolicyPreviewResponse(
        resolved_level=level,
        matched_policy_id=policy.id if policy else None,
        matched_scope_key=matched_scope,
        matched_action_pattern=matched_pattern,
    )
