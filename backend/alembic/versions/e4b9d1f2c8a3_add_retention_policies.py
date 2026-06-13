"""add retention_policies + 2 retention audit events (P0.7b)

Per-tenant, per-table data retention. The retention worker deletes log rows older
than retention_days for each enabled policy.

Enum values use member NAMES (uppercase) — same convention as P0.7 (SQLAlchemy
binds names; the old VALUE-style migrations are the inconsistency, not this).

iCloud note: apply by hand via psql, then
    UPDATE alembic_version SET version_num='e4b9d1f2c8a3';

Revision ID: e4b9d1f2c8a3
Revises: a7e2c9f4b1d8
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "e4b9d1f2c8a3"
down_revision = "a7e2c9f4b1d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for value in ("RETENTION_POLICY_CHANGED", "RETENTION_PURGED"):
        op.execute(f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "retention_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("table_name", sa.String(length=50), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "table_name", name="uq_retention_org_table"),
    )
    op.create_index(
        "ix_retention_policies_organization_id",
        "retention_policies",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_retention_policies_organization_id", table_name="retention_policies")
    op.drop_table("retention_policies")
    # Postgres can't cleanly remove enum values — auditeventtype additions stay.
