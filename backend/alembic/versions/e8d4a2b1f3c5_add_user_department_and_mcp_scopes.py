"""add user.department_id, mcp scope tables, and 4 new audit event types

P0.3.1 Foundation for the MCP Router:
- users.department_id (FK nullable to departments — for MEMBER/VIEWER scope)
- department_agent_permissions (composite PK: dept + agent)
- department_tool_permissions (composite PK: dept + tool_name)
- 4 new auditeventtype values: mcp.route.requested, mcp.route.denied,
  mcp.permission.granted, mcp.permission.revoked

Revision ID: e8d4a2b1f3c5
Revises: e1f9d8c3b7a4
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "e8d4a2b1f3c5"
down_revision = "e1f9d8c3b7a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add department_id to users
    op.add_column(
        "users",
        sa.Column(
            "department_id",
            UUID(as_uuid=True),
            sa.ForeignKey("departments.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_users_department_id", "users", ["department_id"])

    # 2) department_agent_permissions
    op.create_table(
        "department_agent_permissions",
        sa.Column(
            "department_id",
            UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "granted_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("department_id", "agent_id"),
    )

    # 3) department_tool_permissions
    op.create_table(
        "department_tool_permissions",
        sa.Column(
            "department_id",
            UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column(
            "granted_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("department_id", "tool_name"),
    )

    # 4) Extend the auditeventtype enum with 4 new MCP event types
    for value in (
        "mcp.route.requested",
        "mcp.route.denied",
        "mcp.permission.granted",
        "mcp.permission.revoked",
    ):
        op.execute(f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres does not support removing enum values cleanly — skip in downgrade.
    # In practice, downgrading P0.3 would require draining all audit_log rows
    # that reference these values first.
    op.drop_table("department_tool_permissions")
    op.drop_table("department_agent_permissions")
    op.drop_index("ix_users_department_id", table_name="users")
    op.drop_column("users", "department_id")
