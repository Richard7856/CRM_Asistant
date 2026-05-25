"""add approvals system + autonomy policies + 3 new audit events + 2 new task statuses

P0.5 — Human approval system with 4 autonomy levels.

Adds:
- autonomy_policies (configurable per org+scope+action_pattern)
- approval_requests (the queue + history)
- 3 new auditeventtype values: approval.expired, shadow.action.logged, autonomy.policy.changed
- 2 new taskstatus values: waiting_approval, rejected

Revision ID: f6c9a1d4e5b2
Revises: e8d4a2b1f3c5
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "f6c9a1d4e5b2"
down_revision = "e8d4a2b1f3c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) New enums (just for SQLAlchemy registration)
    op.execute("CREATE TYPE autonomylevel AS ENUM ('0', '1', '2', '3')")
    op.execute(
        "CREATE TYPE approvalstatus AS ENUM ("
        "'pending', 'approved', 'rejected', 'expired', "
        "'shadow_logged', 'auto_executed', 'copilot_notified'"
        ")"
    )

    # 2) Extend auditeventtype enum
    for value in (
        "approval.expired",
        "shadow.action.logged",
        "autonomy.policy.changed",
    ):
        op.execute(f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{value}'")

    # 3) Extend taskstatus enum (case-sensitive — SQLAlchemy generates names from member names)
    for value in ("WAITING_APPROVAL", "REJECTED"):
        op.execute(f"ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS '{value}'")

    # 4) autonomy_policies
    op.create_table(
        "autonomy_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("scope_key", sa.String(length=120), nullable=False),
        sa.Column("action_pattern", sa.String(length=150), nullable=False),
        sa.Column(
            "autonomy_level",
            sa.Enum("0", "1", "2", "3", name="autonomylevel", create_type=False),
            nullable=False,
        ),
        sa.Column("auto_promote_threshold", sa.Integer(), nullable=True),
        sa.Column(
            "created_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_autonomy_policies_organization_id", "autonomy_policies", ["organization_id"])
    op.create_index("ix_autonomy_policies_scope_key", "autonomy_policies", ["scope_key"])

    # 5) approval_requests
    op.create_table(
        "approval_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=150), nullable=False),
        sa.Column("action_input", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "autonomy_level",
            sa.Enum("0", "1", "2", "3", name="autonomylevel", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "approved", "rejected", "expired",
                "shadow_logged", "auto_executed", "copilot_notified",
                name="approvalstatus", create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "approved_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shadow_simulated_output", sa.Text(), nullable=True),
    )
    op.create_index("ix_approval_requests_organization_id", "approval_requests", ["organization_id"])
    op.create_index("ix_approval_requests_agent_id", "approval_requests", ["agent_id"])
    op.create_index("ix_approval_requests_task_id", "approval_requests", ["task_id"])
    op.create_index("ix_approval_requests_action", "approval_requests", ["action"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_approval_requests_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_action", table_name="approval_requests")
    op.drop_index("ix_approval_requests_task_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_agent_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_organization_id", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index("ix_autonomy_policies_scope_key", table_name="autonomy_policies")
    op.drop_index("ix_autonomy_policies_organization_id", table_name="autonomy_policies")
    op.drop_table("autonomy_policies")
    op.execute("DROP TYPE IF EXISTS approvalstatus")
    op.execute("DROP TYPE IF EXISTS autonomylevel")
    # Note: Postgres can't remove enum values cleanly — taskstatus and
    # auditeventtype values are NOT removed in downgrade.
