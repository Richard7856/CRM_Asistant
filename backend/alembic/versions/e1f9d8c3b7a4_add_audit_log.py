"""add_audit_log

Adds the append-only `audit_log` table for compliance forensics.
This is DIFFERENT from `activity_logs` (which is the operational dashboard log):
- audit_log records every sensitive action by humans AND agents
- inputs/outputs are stored as SHA-256 hashes (privacy by design)
- UPDATE is blocked by a PostgreSQL trigger (defense in depth)
- DELETE is allowed only at the DB level (for retention cleanup scripts)

Revision ID: e1f9d8c3b7a4
Revises: d5e8f1c4a9b2
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = "e1f9d8c3b7a4"
down_revision = "d5e8f1c4a9b2"
branch_labels = None
depends_on = None


# Enum values must match app/audit/models.py
AUDIT_EVENT_TYPES = [
    # auth
    "auth.login.success",
    "auth.login.failure",
    "auth.logout",
    "auth.token.refresh",
    # user/org
    "user.created",
    "user.deleted",
    "user.role.changed",
    "org.created",
    # agent
    "agent.created",
    "agent.updated",
    "agent.deleted",
    "agent.prompt.changed",
    # department
    "department.created",
    "department.updated",
    "department.deleted",
    # task
    "task.created",
    "task.executed",
    "task.completed",
    "task.failed",
    "task.cancelled",
    # credential
    "credential.created",
    "credential.updated",
    "credential.deleted",
    # knowledge
    "knowledge.document.uploaded",
    "knowledge.document.deleted",
    # integration
    "integration.connected",
    "integration.disconnected",
    # approval (P0.5)
    "approval.requested",
    "approval.granted",
    "approval.rejected",
]

AUDIT_RESULTS = ["success", "failure", "denied", "partial"]


def upgrade() -> None:
    # 1) Enums
    op.execute(
        "CREATE TYPE auditeventtype AS ENUM ("
        + ", ".join(f"'{v}'" for v in AUDIT_EVENT_TYPES)
        + ")"
    )
    op.execute(
        "CREATE TYPE auditresult AS ENUM ("
        + ", ".join(f"'{v}'" for v in AUDIT_RESULTS)
        + ")"
    )

    # 2) Table
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.Enum(*AUDIT_EVENT_TYPES, name="auditeventtype", create_type=False),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "actor_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "actor_agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id"),
            nullable=True,
        ),
        sa.Column(
            "result",
            sa.Enum(*AUDIT_RESULTS, name="auditresult", create_type=False),
            nullable=False,
            server_default="success",
        ),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("autonomy_level", sa.Integer(), nullable=True),
        sa.Column(
            "approved_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "context",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # 3) Indexes (queries comunes)
    op.create_index("ix_audit_log_organization_id", "audit_log", ["organization_id"])
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])
    op.create_index("ix_audit_log_resource_type", "audit_log", ["resource_type"])
    op.create_index("ix_audit_log_resource_id", "audit_log", ["resource_id"])
    op.create_index("ix_audit_log_actor_user_id", "audit_log", ["actor_user_id"])
    op.create_index("ix_audit_log_actor_agent_id", "audit_log", ["actor_agent_id"])
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])

    # 4) Append-only trigger (defense in depth)
    # We block UPDATE only — DELETE remains allowed for retention scripts (P0.7).
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_log_update()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only — UPDATE is forbidden';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER no_update_audit_log
            BEFORE UPDATE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_update();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS no_update_audit_log ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_update()")
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_agent_id", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_user_id", table_name="audit_log")
    op.drop_index("ix_audit_log_resource_id", table_name="audit_log")
    op.drop_index("ix_audit_log_resource_type", table_name="audit_log")
    op.drop_index("ix_audit_log_event_type", table_name="audit_log")
    op.drop_index("ix_audit_log_organization_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.execute("DROP TYPE IF EXISTS auditresult")
    op.execute("DROP TYPE IF EXISTS auditeventtype")
