"""
Knowledge Base service — business logic for document ingestion and retrieval.
Handles chunking, bulk insert, and search result formatting.
"""
import uuid
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import KnowledgeChunk, KnowledgeDocument
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import (
    DocumentIngestRequest,
    KnowledgeChunkResponse,
    KnowledgeDocumentResponse,
    KnowledgeSearchResult,
)

logger = logging.getLogger(__name__)

# Approximate tokens per word — used to estimate token count without tiktoken
TOKENS_PER_WORD = 1.3


class KnowledgeService:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id
        self.repo = KnowledgeRepository(db, org_id)

    async def ingest_document(
        self,
        data: DocumentIngestRequest,
        user_id: uuid.UUID,
    ) -> KnowledgeDocumentResponse:
        """Create document + bulk-insert its chunks."""
        doc = KnowledgeDocument(
            organization_id=self.org_id,
            department_id=data.document.department_id,
            title=data.document.title,
            description=data.document.description,
            file_type=data.document.file_type or "text",
            source_url=data.document.source_url,
            created_by_user_id=user_id,
        )
        await self.repo.create_document(doc)

        chunks = []
        for chunk_in in data.chunks:
            word_count = len(chunk_in.content.split())
            est_tokens = int(word_count * TOKENS_PER_WORD)

            chunk = KnowledgeChunk(
                document_id=doc.id,
                organization_id=self.org_id,
                department_id=data.document.department_id,
                chunk_index=chunk_in.chunk_index,
                content=chunk_in.content,
                token_count=chunk_in.token_count or est_tokens,
                metadata_=chunk_in.metadata,
            )
            chunks.append(chunk)

        await self.repo.create_chunks_bulk(chunks)
        await self.db.commit()

        chunk_count = await self.repo.count_chunks(doc.id)
        response = KnowledgeDocumentResponse.model_validate(doc)
        response.chunk_count = chunk_count
        return response

    async def search(
        self,
        query: str,
        department_id: uuid.UUID | None = None,
        limit: int = 5,
        search_all: bool = False,
    ) -> list[KnowledgeSearchResult]:
        """Search knowledge base and format results for API response."""
        results = await self.repo.search(query, department_id, limit, search_all=search_all)

        output = []
        for chunk, rank in results:
            output.append(KnowledgeSearchResult(
                chunk=KnowledgeChunkResponse.model_validate(chunk),
                rank=rank,
                document_title=chunk.document.title if chunk.document else "Unknown",
                document_id=chunk.document_id,
                department_id=chunk.department_id,
            ))
        return output

    async def list_documents(
        self,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """List all active documents for this organization."""
        docs, total = await self.repo.list_documents(page=page, size=size)
        chunk_counts = {}
        for doc in docs:
            chunk_counts[doc.id] = await self.repo.count_chunks(doc.id)

        items = []
        for doc in docs:
            r = KnowledgeDocumentResponse.model_validate(doc)
            r.chunk_count = chunk_counts.get(doc.id, 0)
            items.append(r)

        return {"items": items, "total": total, "page": page, "size": size}

    async def delete_document(self, doc_id: uuid.UUID) -> bool:
        """Delete document and all its chunks (cascade)."""
        doc = await self.repo.get_document(doc_id)
        if doc is None:
            return False
        await self.repo.delete_document(doc)
        await self.db.commit()
        return True
