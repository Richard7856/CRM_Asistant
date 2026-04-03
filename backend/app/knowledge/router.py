"""Knowledge Base API router."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.database import get_db
from app.knowledge.schemas import (
    DocumentIngestRequest,
    KnowledgeDocumentResponse,
    KnowledgeSearchResult,
)
from app.knowledge.service import KnowledgeService

router = APIRouter()


def _get_service(
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeService:
    return KnowledgeService(db, current_user.organization_id)


@router.get("/", response_model=dict)
async def list_documents(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    svc: KnowledgeService = Depends(_get_service),
):
    """List all knowledge base documents for the current organization."""
    return await svc.list_documents(page=page, size=size)


@router.post("/", response_model=KnowledgeDocumentResponse, status_code=201)
async def ingest_document(
    payload: DocumentIngestRequest,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ingest a document with pre-chunked content into the knowledge base."""
    svc = KnowledgeService(db, current_user.organization_id)
    return await svc.ingest_document(payload, user_id=current_user.id)


@router.get("/search", response_model=list[KnowledgeSearchResult])
async def search_knowledge(
    q: str = Query(..., min_length=1, description="Search query"),
    department_id: uuid.UUID | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
    svc: KnowledgeService = Depends(_get_service),
):
    """Full-text search across the knowledge base.
    When no department_id is provided (UI admin search), returns results from all
    documents. When called from the agent executor, department_id scopes results.
    """
    # search_all=True when no dept filter → UI sees everything; agents pass their dept_id
    return await svc.search(query=q, department_id=department_id, limit=limit, search_all=department_id is None)


@router.get("/{doc_id}", response_model=KnowledgeDocumentResponse)
async def get_document(
    doc_id: uuid.UUID,
    svc: KnowledgeService = Depends(_get_service),
):
    """Get a specific knowledge document."""
    from app.knowledge.repository import KnowledgeRepository
    repo = KnowledgeRepository(svc.db, svc.org_id)
    doc = await repo.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    r = KnowledgeDocumentResponse.model_validate(doc)
    r.chunk_count = await repo.count_chunks(doc_id)
    return r


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: uuid.UUID,
    svc: KnowledgeService = Depends(_get_service),
):
    """Delete a knowledge document and all its chunks."""
    deleted = await svc.delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
