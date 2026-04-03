/**
 * Knowledge Base API client.
 * Supports document ingestion, listing, deletion, and full-text search.
 */
import apiClient from "./client";

export interface KnowledgeDocument {
  id: string;
  organization_id: string;
  department_id: string | null;
  title: string;
  description: string | null;
  file_type: string | null;
  source_url: string | null;
  is_active: boolean;
  chunk_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeChunkInput {
  content: string;
  chunk_index: number;
  token_count?: number;
  metadata?: Record<string, unknown>;
}

export interface IngestDocumentPayload {
  document: {
    title: string;
    description?: string;
    department_id?: string;
    file_type?: string;
    source_url?: string;
  };
  chunks: KnowledgeChunkInput[];
}

export interface KnowledgeSearchResult {
  chunk: {
    id: string;
    document_id: string;
    chunk_index: number;
    content: string;
    token_count: number | null;
    created_at: string;
  };
  rank: number;
  document_title: string;
  document_id: string;
  department_id: string | null;
}

export interface PaginatedDocuments {
  items: KnowledgeDocument[];
  total: number;
  page: number;
  size: number;
}

export async function listDocuments(params?: {
  page?: number;
  size?: number;
}): Promise<PaginatedDocuments> {
  const { data } = await apiClient.get("/knowledge/", { params });
  return data;
}

export async function ingestDocument(
  payload: IngestDocumentPayload
): Promise<KnowledgeDocument> {
  const { data } = await apiClient.post("/knowledge/", payload);
  return data;
}

export async function deleteDocument(id: string): Promise<void> {
  await apiClient.delete(`/knowledge/${id}`);
}

export async function searchKnowledge(params: {
  q: string;
  department_id?: string;
  limit?: number;
}): Promise<KnowledgeSearchResult[]> {
  const { data } = await apiClient.get("/knowledge/search", { params });
  return data;
}
