"""
Approval queue endpoints — what humans use to keep agents in check.

Restricted to OWNER and ADMIN roles. Eventually (P0.4) refine to allow
department heads to approve only their own dept's requests.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.models import ApprovalStatus
from app.approvals.schemas import ApprovalRequestResponse, RejectRequest
from app.approvals.service import ApprovalService
from app.auth.dependencies import get_current_user, get_org_id, require_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.pagination import PaginatedResponse, PaginationParams

router = APIRouter()

_approver_only = Depends(require_role(UserRole.OWNER, UserRole.ADMIN))


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
    user: User = Depends(get_current_user),
) -> ApprovalService:
    return ApprovalService(db, org_id, actor_user_id=user.id)


@router.get("/", response_model=PaginatedResponse, dependencies=[_approver_only])
async def list_approvals(
    status_filter: ApprovalStatus | None = Query(None, alias="status"),
    agent_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    service: ApprovalService = Depends(_get_service),
):
    """
    List approval requests. Default returns all statuses (pending + history).
    Use status=pending to get the actionable queue.
    """
    items, total = await service.list_requests(
        status=status_filter,
        agent_id=agent_id,
        task_id=task_id,
        page=page, size=size,
    )
    return PaginatedResponse.create(
        [ApprovalRequestResponse.model_validate(i) for i in items],
        total,
        PaginationParams(page=page, size=size),
    )


@router.get(
    "/{approval_id}",
    response_model=ApprovalRequestResponse,
    dependencies=[_approver_only],
)
async def get_approval(
    approval_id: uuid.UUID,
    service: ApprovalService = Depends(_get_service),
):
    try:
        req = await service.get_request(approval_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ApprovalRequestResponse.model_validate(req)


@router.post(
    "/{approval_id}/approve",
    response_model=ApprovalRequestResponse,
    dependencies=[_approver_only],
)
async def approve(
    approval_id: uuid.UUID,
    service: ApprovalService = Depends(_get_service),
    user: User = Depends(get_current_user),
):
    """
    Approve a PENDING request.

    Side effect: if the request is linked to a task in WAITING_APPROVAL,
    the task's executor must be re-dispatched separately. For now, this
    endpoint only changes statuses — the dispatcher integration is in
    the executor (re-runs find the APPROVED state via check_or_request).
    """
    try:
        req = await service.approve(approval_id, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApprovalRequestResponse.model_validate(req)


@router.post(
    "/{approval_id}/reject",
    response_model=ApprovalRequestResponse,
    dependencies=[_approver_only],
)
async def reject(
    approval_id: uuid.UUID,
    body: RejectRequest,
    service: ApprovalService = Depends(_get_service),
    user: User = Depends(get_current_user),
):
    """
    Reject a PENDING request with a written reason.
    The associated task (if any) ends up in REJECTED status.
    """
    try:
        req = await service.reject(approval_id, user.id, body.reason)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApprovalRequestResponse.model_validate(req)
