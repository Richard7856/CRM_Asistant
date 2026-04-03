import apiClient from "./client";
import type { AgentInteraction, InteractionGraphData } from "@/types/interaction";
import type { PaginatedResponse } from "@/types/common";

export async function listInteractions(params?: {
  agent_id?: string;
  channel?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  size?: number;
}): Promise<PaginatedResponse<AgentInteraction>> {
  const { data } = await apiClient.get("/interactions/", { params });
  return data;
}

export async function createInteraction(interaction: {
  from_agent_id: string;
  to_agent_id: string;
  channel: string;
  task_id?: string;
  payload_summary?: string;
  payload?: Record<string, unknown>;
  latency_ms?: number;
  success?: boolean;
}): Promise<AgentInteraction> {
  const { data } = await apiClient.post("/interactions/", interaction);
  return data;
}

export async function getInteractionGraph(): Promise<InteractionGraphData> {
  const { data } = await apiClient.get("/interactions/graph");
  return data;
}
