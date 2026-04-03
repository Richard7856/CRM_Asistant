"""add_organization_id_to_all_models

Revision ID: c64dcc61a16a
Revises: 7a57a29178cc
Create Date: 2026-03-31 16:46:33.006491

Strategy: add column as nullable → backfill existing rows with the first
organization → alter to non-nullable → add index + FK.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c64dcc61a16a'
down_revision: Union[str, None] = '7a57a29178cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    'agents', 'departments', 'tasks', 'activity_logs',
    'agent_interactions', 'performance_metrics', 'improvement_points',
]


def upgrade() -> None:
    conn = op.get_bind()

    # Get first org for backfill
    result = conn.execute(sa.text("SELECT id FROM organizations LIMIT 1"))
    row = result.first()
    default_org_id = row[0] if row else None

    for table in TABLES:
        # 1. Add as nullable
        op.add_column(table, sa.Column('organization_id', sa.UUID(), nullable=True))

        # 2. Backfill existing rows
        if default_org_id is not None:
            conn.execute(
                sa.text(f"UPDATE {table} SET organization_id = :org_id WHERE organization_id IS NULL"),
                {"org_id": default_org_id},
            )

        # 3. Make non-nullable
        op.alter_column(table, 'organization_id', nullable=False)

        # 4. Add index and FK
        op.create_index(
            op.f(f'ix_{table}_organization_id'), table, ['organization_id'], unique=False
        )
        op.create_foreign_key(None, table, 'organizations', ['organization_id'], ['id'])


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(None, table, type_='foreignkey')
        op.drop_index(op.f(f'ix_{table}_organization_id'), table_name=table)
        op.drop_column(table, 'organization_id')
