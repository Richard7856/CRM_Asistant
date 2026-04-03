"""add_rag_knowledge_base

Revision ID: a3f892bc1d47
Revises: fa1356ecb1a6
Create Date: 2026-04-03

Two new tables for RAG (Retrieval Augmented Generation):
  knowledge_documents — document metadata
  knowledge_chunks — searchable text segments with GIN tsvector index
A PostgreSQL trigger auto-updates search_vector on content change.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a3f892bc1d47'
down_revision = 'c64dcc61a16a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- knowledge_documents ---
    op.create_table(
        'knowledge_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('department_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('file_type', sa.String(50), nullable=True),
        sa.Column('source_url', sa.String(500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_knowledge_documents_organization_id', 'knowledge_documents', ['organization_id'])
    op.create_index('ix_knowledge_documents_department_id', 'knowledge_documents', ['department_id'])

    # --- knowledge_chunks ---
    op.create_table(
        'knowledge_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('department_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('search_vector', postgresql.TSVECTOR(), nullable=False, server_default=sa.text("''::tsvector")),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['document_id'], ['knowledge_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_knowledge_chunks_search_vector',
        'knowledge_chunks', ['search_vector'],
        postgresql_using='gin',
    )
    op.create_index('ix_knowledge_chunks_org_dept', 'knowledge_chunks', ['organization_id', 'department_id'])
    op.create_index('ix_knowledge_chunks_document_id', 'knowledge_chunks', ['document_id'])

    # Trigger: auto-update search_vector whenever content changes
    # Uses 'simple' config (language-agnostic, works for Spanish + English)
    op.execute("""
        CREATE OR REPLACE FUNCTION knowledge_chunks_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('pg_catalog.simple', coalesce(NEW.content, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER knowledge_chunks_tsvector_trigger
        BEFORE INSERT OR UPDATE OF content
        ON knowledge_chunks
        FOR EACH ROW EXECUTE FUNCTION knowledge_chunks_search_vector_update();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS knowledge_chunks_tsvector_trigger ON knowledge_chunks")
    op.execute("DROP FUNCTION IF EXISTS knowledge_chunks_search_vector_update")
    op.drop_table('knowledge_chunks')
    op.drop_table('knowledge_documents')
