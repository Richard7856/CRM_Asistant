"""
Audit log — append-only compliance trail.

This is DIFFERENT from ActivityLog (which is the operational log shown in the
dashboard). AuditLog is for forensics and compliance auditors:
- Records EVERY sensitive action by humans AND agents
- Inputs and outputs are hashed (SHA-256) for forensics
- Append-only enforced at the DB level (trigger blocks UPDATE)
- Records autonomy level + approver for actions that went through approval

Retention policy is configurable per tenant (default 7 years for banking/insurance).
DELETE is permitted at the DB level only for retention cleanup scripts —
never exposed via API.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditEventType(str, enum.Enum):
    """
    Every sensitive action that must leave an audit trail.
    Naming convention: <domain>.<noun>.<verb_or_outcome>
    """

    # ─── Authentication ───
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    TOKEN_REFRESH = "auth.token.refresh"

    # ─── Users & Organizations ───
    USER_CREATED = "user.created"
    USER_DELETED = "user.deleted"
    USER_ROLE_CHANGED = "user.role.changed"
    ORG_CREATED = "org.created"

    # ─── Agents ───
    AGENT_CREATED = "agent.created"
    AGENT_UPDATED = "agent.updated"
    AGENT_DELETED = "agent.deleted"
    AGENT_PROMPT_CHANGED = "agent.prompt.changed"

    # ─── Departments ───
    DEPARTMENT_CREATED = "department.created"
    DEPARTMENT_UPDATED = "department.updated"
    DEPARTMENT_DELETED = "department.deleted"

    # ─── Tasks ───
    TASK_CREATED = "task.created"
    TASK_EXECUTED = "task.executed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"

    # ─── Credentials ───
    # (READ access is in credential_access_log — not duplicated here)
    CREDENTIAL_CREATED = "credential.created"
    CREDENTIAL_UPDATED = "credential.updated"
    CREDENTIAL_DELETED = "credential.deleted"

    # ─── Knowledge ───
    DOCUMENT_UPLOADED = "knowledge.document.uploaded"
    DOCUMENT_DELETED = "knowledge.document.deleted"

    # ─── Integrations ───
    INTEGRATION_CONNECTED = "integration.connected"
    INTEGRATION_DISCONNECTED = "integration.disconnected"

    # ─── Human approval (placeholder for P0.5) ───
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"

    # ─── MCP Router (P0.3) ───
    MCP_ROUTE_REQUESTED = "mcp.route.requested"
    MCP_ROUTE_DENIED = "mcp.route.denied"
    MCP_PERMISSION_GRANTED = "mcp.permission.granted"
    MCP_PERMISSION_REVOKED = "mcp.permission.revoked"

    # ─── Approval system (P0.5) ───
    APPROVAL_EXPIRED = "approval.expired"
    SHADOW_ACTION_LOGGED = "shadow.action.logged"
    AUTONOMY_POLICY_CHANGED = "autonomy.policy.changed"

    # ─── Compliance / LFPDPPP (P0.7) ───
    # TENANT_ERASED is defined for symmetry but is NOT written to audit_log —
    # a tenant erasure deletes its own audit_log, so the durable record is the
    # ErasureCertificate instead. USER_ERASED and DATA_EXPORTED keep the org alive
    # and are logged normally.
    TENANT_ERASED = "compliance.tenant.erased"
    USER_ERASED = "compliance.user.erased"
    DATA_EXPORTED = "compliance.data.exported"


class AuditResult(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    PARTIAL = "partial"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[AuditEventType] = mapped_column(nullable=False, index=True)

    # What was affected (optional — some events like LOGIN don't have a resource)
    resource_type: Mapped[str | None] = mapped_column(String(50), index=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    # Who did it — exactly one of these is set in practice
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    actor_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), index=True
    )

    result: Mapped[AuditResult] = mapped_column(default=AuditResult.SUCCESS, nullable=False)

    # SHA-256 hex digests of input/output (64 chars). NULL when not applicable.
    # Stores hash, not content — privacy by design.
    input_hash: Mapped[str | None] = mapped_column(String(64))
    output_hash: Mapped[str | None] = mapped_column(String(64))

    # Approval context (filled in starting from P0.5 — human approval system)
    autonomy_level: Mapped[int | None] = mapped_column(Integer)  # 0=Shadow, 1=Auto, 2=Co-pilot, 3=Manual
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    # Free-form context (IP address, user agent, custom fields, error message...)
    context: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
