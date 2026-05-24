"""Pydantic schemas for audit log responses + filters."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.audit.models import AuditEventType, AuditResult


class AuditLogResponse(BaseModel):
    """API response for an audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    event_type: AuditEventType
    resource_type: str | None
    resource_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    actor_agent_id: uuid.UUID | None
    result: AuditResult
    input_hash: str | None
    output_hash: str | None
    autonomy_level: int | None
    approved_by_user_id: uuid.UUID | None
    context: dict
    occurred_at: datetime
