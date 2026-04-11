import apiClient from "./client";
import type { Credential, CreateCredential, UpdateCredential } from "@/types/credential";
import type { PaginatedResponse } from "@/types/common";

export async function listCredentials(params?: {
  page?: number;
  size?: number;
  service_name?: string;
  agent_id?: string;
  is_active?: boolean;
}): Promise<PaginatedResponse<Credential>> {
  const { data } = await apiClient.get("/credentials/", { params });
  return data;
}

export async function getCredential(id: string): Promise<Credential> {
  const { data } = await apiClient.get(`/credentials/${id}`);
  return data;
}

export async function listAgentCredentials(agentId: string): Promise<Credential[]> {
  const { data } = await apiClient.get(`/credentials/agent/${agentId}`);
  return data;
}

export async function createCredential(cred: CreateCredential): Promise<Credential> {
  const { data } = await apiClient.post("/credentials/", cred);
  return data;
}

export async function updateCredential(
  id: string,
  updates: UpdateCredential
): Promise<Credential> {
  const { data } = await apiClient.patch(`/credentials/${id}`, updates);
  return data;
}

export async function deleteCredential(id: string): Promise<void> {
  await apiClient.delete(`/credentials/${id}`);
}
