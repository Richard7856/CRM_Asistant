import apiClient from "./client";
import type { ImprovementPoint, CreateImprovement } from "@/types/improvement";
import type { PaginatedResponse } from "@/types/common";

export async function listImprovements(params?: {
  agent_id?: string;
  status?: string;
  category?: string;
  priority?: string;
  page?: number;
  size?: number;
}): Promise<PaginatedResponse<ImprovementPoint>> {
  const { data } = await apiClient.get("/improvements/", { params });
  return data;
}

export async function createImprovement(improvement: CreateImprovement): Promise<ImprovementPoint> {
  const { data } = await apiClient.post("/improvements/", improvement);
  return data;
}

export async function updateImprovement(id: string, updates: Partial<ImprovementPoint>): Promise<ImprovementPoint> {
  const { data } = await apiClient.patch(`/improvements/${id}`, updates);
  return data;
}
