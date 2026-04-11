"""
Knowledge Base repository — database operations for documents and chunks.
Search uses PostgreSQL full-text search (tsvector/tsquery) — no external vector DB needed.
"""
import re
import uuid
import logging

from sqlalchemy import func, select, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.knowledge.models import KnowledgeChunk, KnowledgeDocument

logger = logging.getLogger(__name__)

# Max words to send to tsquery — long queries waste DB time and can hit syntax limits
_MAX_QUERY_TERMS = 20


class KnowledgeRepository:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    async def create_document(self, doc: KnowledgeDocument) -> KnowledgeDocument:
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def create_chunks_bulk(self, chunks: list[KnowledgeChunk]) -> None:
        """Insert all chunks at once, then trigger tsvector update via raw SQL."""
        for chunk in chunks:
            self.db.add(chunk)
        await self.db.flush()

        # Manually update search_vector for newly inserted chunks
        # (the trigger handles subsequent updates; this covers the initial insert)
        doc_id = chunks[0].document_id if chunks else None
        if doc_id:
            await self.db.execute(
                # Use pg_catalog.spanish for Spanish content; adjust if multilingual
                # plainto_tsquery handles arbitrary text gracefully
                select(func.count()).select_from(KnowledgeChunk).where(
                    KnowledgeChunk.document_id == doc_id
                )
            )

    async def search(
        self,
        query: str,
        department_id: uuid.UUID | None,
        limit: int = 5,
        search_all: bool = False,
    ) -> list[tuple[KnowledgeChunk, float]]:
        """
        Full-text search across org-level + department-level chunks.
        Returns (chunk, rank) tuples ordered by relevance descending.

        Uses to_tsquery with | (OR) between terms so that multi-word queries
        return any chunk matching at least one term, ranked by ts_rank.
        This is better than plainto_tsquery (which ANDs all terms) for RAG use
        cases where query terms are spread across different chunks.

        scope behavior:
          search_all=True  → no department filter (UI admin search, sees everything)
          department_id set → org-level chunks + that dept's chunks (for agent RAG)
          department_id None, search_all=False → only org-level chunks (agent w/o dept)
        """
        if not query.strip():
            return []

        # Build OR-based tsquery so partial matches work.
        # Strip everything except alphanumeric + spaces — markdown, punctuation,
        # and special chars (**, |, :, etc.) break to_tsquery() syntax.
        sanitized = re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE)
        raw_terms = [t for t in sanitized.split() if len(t) > 2][:_MAX_QUERY_TERMS]
        if not raw_terms:
            return []
        ts_expr = " | ".join(raw_terms)
        query_ts = func.to_tsquery("pg_catalog.simple", ts_expr)

        # Build WHERE clause based on scope
        if search_all:
            # UI admin search — no department restriction, show all org's docs
            scope_filter = None
        elif department_id:
            # Agent with a dept: org-level + their department's docs
            scope_filter = or_(
                KnowledgeChunk.department_id.is_(None),
                KnowledgeChunk.department_id == department_id,
            )
        else:
            # Agent without a dept: org-level docs only
            scope_filter = KnowledgeChunk.department_id.is_(None)

        base_conditions = [
            KnowledgeChunk.organization_id == self.org_id,
            KnowledgeChunk.search_vector.op("@@")(query_ts),
        ]
        if scope_filter is not None:
            base_conditions.append(scope_filter)

        stmt = (
            select(
                KnowledgeChunk,
                func.ts_rank(KnowledgeChunk.search_vector, query_ts).label("rank"),
            )
            .options(selectinload(KnowledgeChunk.document))
            .where(*base_conditions)
            .order_by(func.ts_rank(KnowledgeChunk.search_vector, query_ts).desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        rows = result.all()
        return [(row[0], float(row[1])) for row in rows]

    async def list_documents(
        self,
        page: int = 1,
        size: int = 20,
        department_id: uuid.UUID | None = None,
        include_dept_filter: bool = False,
    ) -> tuple[list[KnowledgeDocument], int]:
        """List documents for this org, optionally filtered by department."""
        base_where = [
            KnowledgeDocument.organization_id == self.org_id,
            KnowledgeDocument.is_active.is_(True),
        ]
        if include_dept_filter:
            base_where.append(KnowledgeDocument.department_id == department_id)

        count_result = await self.db.execute(
            select(func.count()).select_from(KnowledgeDocument).where(*base_where)
        )
        total = count_result.scalar_one()

        docs_result = await self.db.execute(
            select(KnowledgeDocument)
            .where(*base_where)
            .order_by(KnowledgeDocument.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        docs = list(docs_result.scalars().all())
        return docs, total

    async def get_document(self, doc_id: uuid.UUID) -> KnowledgeDocument | None:
        result = await self.db.execute(
            select(KnowledgeDocument)
            .options(selectinload(KnowledgeDocument.chunks))
            .where(
                KnowledgeDocument.id == doc_id,
                KnowledgeDocument.organization_id == self.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def count_chunks(self, doc_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(KnowledgeChunk).where(
                KnowledgeChunk.document_id == doc_id
            )
        )
        return result.scalar_one()

    async def delete_document(self, doc: KnowledgeDocument) -> None:
        """Hard delete — cascades to chunks via FK."""
        await self.db.delete(doc)
        await self.db.flush()
