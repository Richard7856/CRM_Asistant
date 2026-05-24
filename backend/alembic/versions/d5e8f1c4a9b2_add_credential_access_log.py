"""add_credential_access_log

Adds the audit table for credential reads.
Every call to CredentialService.get_credential_value() generates a row here.

Note: this migration does NOT touch existing rows in `credentials`. From the
moment this lands, all new/updated credentials are stored encrypted via Fernet
(see app/credentials/encryption.py). Pre-existing rows in dev databases will
be left as plaintext — wipe and recreate them via the API.

Revision ID: d5e8f1c4a9b2
Revises: 3313605f6b2a
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "d5e8f1c4a9b2"
down_revision = "3313605f6b2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credential_access_log",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "credential_id",
            UUID(as_uuid=True),
            sa.ForeignKey("credentials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "accessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "context",
            sa.String(length=200),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_credential_access_log_credential_id",
        "credential_access_log",
        ["credential_id"],
    )
    op.create_index(
        "ix_credential_access_log_agent_id",
        "credential_access_log",
        ["agent_id"],
    )
    op.create_index(
        "ix_credential_access_log_user_id",
        "credential_access_log",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_credential_access_log_user_id", table_name="credential_access_log"
    )
    op.drop_index(
        "ix_credential_access_log_agent_id", table_name="credential_access_log"
    )
    op.drop_index(
        "ix_credential_access_log_credential_id", table_name="credential_access_log"
    )
    op.drop_table("credential_access_log")
