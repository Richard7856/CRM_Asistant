import apiClient from "./client";
import type { Agent, AgentDetail, CreateInternalAgent, RegisterExternalAgent, Role } from "@/types/agent";
import type { PaginatedResponse } from "@/types/common";

export async function listAgents(params?: {
  page?: number;
  size?: number;
  department_id?: string;
  status?: string;
  origin?: string;
}): Promise<PaginatedResponse<Agent>> {
  const { data } = await apiClient.get("/agents/", { params });
  return data;
}

export async function getAgent(id: string): Promise<AgentDetail> {
  const { data } = await apiClient.get(`/agents/${id}`);
  return data;
}

export async function createInternalAgent(agent: CreateInternalAgent): Promise<Agent> {
  const { data } = await apiClient.post("/agents/", agent);
  return data;
}

export async function registerExternalAgent(agent: RegisterExternalAgent): Promise<{ agent: Agent; api_key: string }> {
  const { data } = await apiClient.post("/agents/register/", agent);
  return data;
}

export async function updateAgent(id: string, updates: Partial<Agent>): Promise<Agent> {
  const { data } = await apiClient.patch(`/agents/${id}`, updates);
  return data;
}

export async function deleteAgent(id: string): Promise<void> {
  await apiClient.delete(`/agents/${id}`);
}

export async function getSubordinates(id: string): Promise<Agent[]> {
  const { data } = await apiClient.get(`/agents/${id}/subordinates`);
  return data;
}

export async function sendHeartbeat(id: string): Promise<void> {
  await apiClient.post(`/agents/${id}/heartbeat`);
}

export async function listRoles(): Promise<Role[]> {
  const { data } = await apiClient.get("/agents/roles/");
  return data;
}
