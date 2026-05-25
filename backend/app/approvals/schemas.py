"""Pydantic schemas for the approval system."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.approvals.models import ApprovalStatus, AutonomyLevel


# ─── ApprovalRequest schemas ───


class ApprovalRequestResponse(BaseModel):
    """The full payload a human reviewer sees in the approval queue."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    agent_id: uuid.UUID
    task_id: uuid.UUID | None
    action: str
    action_input: dict
    autonomy_level: AutonomyLevel
    status: ApprovalStatus
    approved_by_user_id: uuid.UUID | None
    rejected_reason: str | None
    requested_at: datetime
    decided_at: datetime | None
    expires_at: datetime | None
    shadow_simulated_output: str | None


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


# ─── AutonomyPolicy schemas ───


class AutonomyPolicyCreate(BaseModel):
    scope_key: str = Field(..., min_length=1, max_length=120)
    action_pattern: str = Field(..., min_length=1, max_length=150)
    autonomy_level: AutonomyLevel
    auto_promote_threshold: int | None = Field(None, ge=1)


class AutonomyPolicyUpdate(BaseModel):
    autonomy_level: AutonomyLevel | None = None
    auto_promote_threshold: int | None = Field(None, ge=1)


class AutonomyPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    scope_key: str
    action_pattern: str
    autonomy_level: AutonomyLevel
    auto_promote_threshold: int | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PolicyPreviewRequest(BaseModel):
    """For 'what level would apply if I tried this combo?' tooling."""

    agent_id: uuid.UUID
    action: str = Field(..., min_length=1, max_length=150)


class PolicyPreviewResponse(BaseModel):
    resolved_level: AutonomyLevel
    matched_policy_id: uuid.UUID | None
    matched_scope_key: str | None  # "global" / "dept:<id>" / "agent:<id>" / "default"
    matched_action_pattern: str | None
