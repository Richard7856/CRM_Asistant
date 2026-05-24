"""
Audit log API — read-only access for compliance auditors and org owners.

Restricted to roles: OWNER and ADMIN. Regular members/viewers cannot read
the audit log because it can contain sensitive context (IPs, error messages,
references to other users' actions).

CSV export caps at 10k rows for now. Streaming + retention cleanup is P0.7.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEventType, AuditResult
from app.audit.schemas import AuditLogResponse
from app.audit.service import AuditService
from app.auth.dependencies import get_org_id, require_role
from app.auth.models import UserRole
from app.core.database import get_db
from app.core.pagination import PaginatedResponse, PaginationParams

router = APIRouter()

# Only OWNER + ADMIN can read the audit log.
_audit_reader = Depends(require_role(UserRole.OWNER, UserRole.ADMIN))


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
) -> AuditService:
    return AuditService(db, org_id)


@router.get("/", response_model=PaginatedResponse, dependencies=[_audit_reader])
async def list_audit_events(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    event_type: AuditEventType | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_agent_id: uuid.UUID | None = None,
    result: AuditResult | None = None,
    from_ts: datetime | None = Query(None, description="ISO 8601 lower bound for occurred_at"),
    to_ts: datetime | None = Query(None, description="ISO 8601 upper bound for occurred_at"),
    service: AuditService = Depends(_get_service),
):
    items, total = await service.list_events(
        page=page, size=size,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_user_id=actor_user_id,
        actor_agent_id=actor_agent_id,
        result=result,
        from_ts=from_ts, to_ts=to_ts,
    )
    return PaginatedResponse.create(
        [AuditLogResponse.model_validate(i) for i in items],
        total,
        PaginationParams(page=page, size=size),
    )


@router.get("/export.csv", dependencies=[_audit_reader])
async def export_audit_csv(
    event_type: AuditEventType | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_agent_id: uuid.UUID | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    service: AuditService = Depends(_get_service),
) -> Response:
    """
    Export filtered audit log as CSV. Capped at 10k rows.
    For larger exports, use date ranges to chunk the data.
    """
    csv_str = await service.export_csv(
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_user_id=actor_user_id,
        actor_agent_id=actor_agent_id,
        from_ts=from_ts, to_ts=to_ts,
    )
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="audit_log.csv"',
        },
    )
