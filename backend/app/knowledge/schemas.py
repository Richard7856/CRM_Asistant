"""Pydantic schemas for the Knowledge Base API."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeChunkInput(BaseModel):
    content: str = Field(..., min_length=1)
    chunk_index: int = Field(..., ge=0)
    token_count: int | None = None
    metadata: dict = Field(default_factory=dict)


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = None
    department_id: uuid.UUID | None = None  # None = org-level
    file_type: str | None = None
    source_url: str | None = None


class DocumentIngestRequest(BaseModel):
    """Full ingest payload: document metadata + pre-chunked content."""
    document: KnowledgeDocumentCreate
    chunks: list[KnowledgeChunkInput] = Field(..., min_length=1)


class KnowledgeChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int | None
    created_at: datetime


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    department_id: uuid.UUID | None
    title: str
    description: str | None
    file_type: str | None
    source_url: str | None
    is_active: bool
    chunk_count: int | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchResult(BaseModel):
    chunk: KnowledgeChunkResponse
    rank: float
    document_title: str
    document_id: uuid.UUID
    department_id: uuid.UUID | None
