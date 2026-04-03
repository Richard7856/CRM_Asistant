import apiClient from "./client";
import type {
  PromptVersion,
  PromptTemplate,
  CreatePromptVersion,
  CreatePromptTemplate,
  PromptCompareResponse,
} from "@/types/prompt";
import type { PaginatedResponse } from "@/types/common";

// ── Templates ──────────────────────────────────────────────

export async function listTemplates(params?: {
  category?: string;
  search?: string;
  page?: number;
  size?: number;
}): Promise<PaginatedResponse<PromptTemplate>> {
  const { data } = await apiClient.get("/prompts/templates", { params });
  return data;
}

export async function getTemplate(id: string): Promise<PromptTemplate> {
  const { data } = await apiClient.get(`/prompts/templates/${id}`);
  return data;
}

export async function createTemplate(
  template: CreatePromptTemplate
): Promise<PromptTemplate> {
  const { data } = await apiClient.post("/prompts/templates", template);
  return data;
}

export async function updateTemplate(
  id: string,
  updates: Partial<CreatePromptTemplate>
): Promise<PromptTemplate> {
  const { data } = await apiClient.patch(`/prompts/templates/${id}`, updates);
  return data;
}

export async function deleteTemplate(id: string): Promise<void> {
  await apiClient.delete(`/prompts/templates/${id}`);
}

// ── Agent Prompt Versions ──────────────────────────────────

export async function listVersions(
  agentId: string,
  params?: { page?: number; size?: number }
): Promise<PaginatedResponse<PromptVersion>> {
  const { data } = await apiClient.get(
    `/prompts/agents/${agentId}/versions`,
    { params }
  );
  return data;
}

export async function createVersion(
  agentId: string,
  version: CreatePromptVersion
): Promise<PromptVersion> {
  const { data } = await apiClient.post(
    `/prompts/agents/${agentId}/versions`,
    version
  );
  return data;
}

export async function activateVersion(
  agentId: string,
  versionNumber: number
): Promise<PromptVersion> {
  const { data } = await apiClient.post(
    `/prompts/agents/${agentId}/versions/${versionNumber}/activate`
  );
  return data;
}

export async function compareVersions(
  agentId: string,
  v1: number,
  v2: number
): Promise<PromptCompareResponse> {
  const { data } = await apiClient.get(
    `/prompts/agents/${agentId}/versions/compare`,
    { params: { v1, v2 } }
  );
  return data;
}

export async function applyTemplate(
  agentId: string,
  templateId: string
): Promise<PromptVersion> {
  const { data } = await apiClient.post(
    `/prompts/agents/${agentId}/apply-template/${templateId}`
  );
  return data;
}
