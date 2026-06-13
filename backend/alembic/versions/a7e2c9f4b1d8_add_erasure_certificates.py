"""add erasure_certificates + 3 compliance audit events (P0.7 LFPDPPP)

Adds:
- erasure_certificates: the durable, immutable proof of a data erasure. NOT a
  foreign key to organizations (it must outlive the org it describes). A trigger
  blocks BOTH update and delete — stronger than audit_log (which allows DELETE for
  retention) because a proof of erasure that can itself be erased is worthless.
- 2 new enums: erasuresubjecttype, erasuremethod
- 3 new auditeventtype values: compliance events

IMPORTANT — enum labels use MEMBER NAMES (uppercase), not the dotted values.
SQLAlchemy's Enum binds the member NAME at runtime (verified: AuditEventType.X
binds 'X'), and Base.metadata.create_all (test DB) creates the labels from names
too. The older auditeventtype migration used the lowercase dotted VALUES, which
does NOT match what the ORM binds — a latent inconsistency to clean up in P0.8.
New code uses names so dev/prod matches both the ORM and the test DB.

iCloud note: alembic autogenerate/upgrade hangs in this repo (path with spaces).
Apply by hand via psql, then: UPDATE alembic_version SET version_num='a7e2c9f4b1d8';

Revision ID: a7e2c9f4b1d8
Revises: f6c9a1d4e5b2
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "a7e2c9f4b1d8"
down_revision = "f6c9a1d4e5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) New enums (member NAMES — matches ORM bind + create_all)
    op.execute("CREATE TYPE erasuresubjecttype AS ENUM ('TENANT', 'USER')")
    op.execute("CREATE TYPE erasuremethod AS ENUM ('ORDERED_DELETE', 'ANONYMIZE')")

    # 2) Extend auditeventtype with the compliance events (member NAMES)
    for value in ("TENANT_ERASED", "USER_ERASED", "DATA_EXPORTED"):
        op.execute(f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{value}'")

    # 3) erasure_certificates table
    op.create_table(
        "erasure_certificates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        # Snapshots — deliberately NOT foreign keys (the org may be gone).
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("organization_name", sa.String(length=120), nullable=False),
        sa.Column("organization_slug", sa.String(length=60), nullable=False),
        sa.Column(
            "subject_type",
            sa.Enum("TENANT", "USER", name="erasuresubjecttype", create_type=False),
            nullable=False,
        ),
        sa.Column("subject_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "method",
            sa.Enum("ORDERED_DELETE", "ANONYMIZE", name="erasuremethod", create_type=False),
            nullable=False,
        ),
        sa.Column("requested_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by_email", sa.String(length=255), nullable=True),
        sa.Column("row_counts", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("total_rows_erased", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_erasure_certificates_organization_id",
        "erasure_certificates",
        ["organization_id"],
    )
    op.create_index(
        "ix_erasure_certificates_issued_at",
        "erasure_certificates",
        ["issued_at"],
    )

    # 4) Immutability: block UPDATE and DELETE on certificates.
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_erasure_certificate_change()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'erasure_certificates is immutable — % is forbidden', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER no_change_erasure_certificates
            BEFORE UPDATE OR DELETE ON erasure_certificates
            FOR EACH ROW EXECUTE FUNCTION prevent_erasure_certificate_change();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS no_change_erasure_certificates ON erasure_certificates")
    op.execute("DROP FUNCTION IF EXISTS prevent_erasure_certificate_change()")
    op.drop_index("ix_erasure_certificates_issued_at", table_name="erasure_certificates")
    op.drop_index("ix_erasure_certificates_organization_id", table_name="erasure_certificates")
    op.drop_table("erasure_certificates")
    op.execute("DROP TYPE IF EXISTS erasuremethod")
    op.execute("DROP TYPE IF EXISTS erasuresubjecttype")
    # Postgres can't cleanly remove enum values — auditeventtype additions stay.
