"""
Approval system — the human-in-the-loop layer of the product.

4 autonomy levels per the ROADMAP V3.1:
- 0 SHADOW   — agent observes inputs, registers what it WOULD do, never executes
- 1 AUTO     — agent executes without asking, fully audited and reversible
- 2 COPILOT  — agent executes + notifies human (in-app today, WhatsApp/email later)
- 3 MANUAL   — agent prepares, human approves BEFORE execution (default)

Two tables:
- AutonomyPolicy: configurable per (org, scope, action_pattern) → level
- ApprovalRequest: the queue of pending decisions + history of past ones

Non-overridable rules (hardcoded in service, not in DB):
- DELETE:* always Level 3 (no policy can lower it)
- Missing policy → Level 3 default (more secure than the alternative)
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AutonomyLevel(int, enum.Enum):
    SHADOW = 0   # observe but never execute
    AUTO = 1     # execute without asking
    COPILOT = 2  # execute + notify
    MANUAL = 3   # human approves before execution


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"                   # waiting for human decision (Level 3)
    APPROVED = "approved"                 # human approved — agent resumes
    REJECTED = "rejected"                 # human rejected — task ends as REJECTED
    EXPIRED = "expired"                   # nobody responded in time
    SHADOW_LOGGED = "shadow_logged"       # Level 0 — recorded, never executed
    AUTO_EXECUTED = "auto_executed"       # Level 1 — already ran
    COPILOT_NOTIFIED = "copilot_notified" # Level 2 — ran + notified human


class AutonomyPolicy(Base):
    """
    A single policy row. The service resolves the effective level by walking
    a precedence chain — see ApprovalService.resolve_level().
    """

    __tablename__ = "autonomy_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    # Scope of this policy. Possible values:
    #   "global"              — applies to all agents/depts in the org
    #   "dept:<dept_uuid>"    — applies to agents in that department
    #   "agent:<agent_uuid>"  — applies to that single agent only
    # The service queries each scope from most specific to least.
    scope_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    # Action this policy covers. Patterns:
    #   "*"                — anything
    #   "<exact_name>"     — exact match (e.g. "assign_task")
    #   "<prefix>:*"       — anything starting with prefix (e.g. "DELETE:*")
    action_pattern: Mapped[str] = mapped_column(String(150), nullable=False)

    autonomy_level: Mapped[AutonomyLevel] = mapped_column(nullable=False)

    # When set, the system suggests demoting (e.g. from MANUAL to COPILOT) after
    # this many consecutive APPROVED requests. UI surfaces the suggestion;
    # the admin confirms before applying. Null = no auto-suggest.
    auto_promote_threshold: Mapped[int | None] = mapped_column(Integer)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class ApprovalRequest(Base):
    """
    One row per (task, action) that ever passed through the approval system.

    For Levels 0/1/2: created with a terminal status (SHADOW_LOGGED /
    AUTO_EXECUTED / COPILOT_NOTIFIED). Useful as history.

    For Level 3: created PENDING, transitioned by human action to APPROVED /
    REJECTED, or by the cron worker to EXPIRED.
    """

    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )

    # The agent that wanted to run the action
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    # The task this action was part of (null if approval came from a non-task path)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), index=True
    )

    # Tool/action name + the input that would be passed to it. The input is
    # stored as JSONB so the human reviewer sees exactly what would execute.
    action: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    action_input: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # The level applied to this specific request (snapshot of resolve_level)
    autonomy_level: Mapped[AutonomyLevel] = mapped_column(nullable=False)

    status: Mapped[ApprovalStatus] = mapped_column(
        nullable=False, default=ApprovalStatus.PENDING
    )

    # Who decided (null if SHADOW/AUTO/EXPIRED — no human involved)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    rejected_reason: Mapped[str | None] = mapped_column(Text)

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Shadow-mode only — what the agent claimed it would have done.
    # In MVP this is the LLM's text output AFTER seeing the "shadow_mode=True"
    # response from the fake execute_tool. The human can read it to gauge intent.
    shadow_simulated_output: Mapped[str | None] = mapped_column(Text)

    # Relationships (lightweight — most queries don't need them)
    agent = relationship("Agent", foreign_keys=[agent_id])
    task = relationship("Task", foreign_keys=[task_id])
