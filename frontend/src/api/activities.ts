import apiClient from "./client";
import type { ActivityLog } from "@/types/activity";
import type { PaginatedResponse } from "@/types/common";

export async function listActivities(params?: {
  page?: number;
  size?: number;
  agent_id?: string;
  task_id?: string;
  level?: string;
  date_from?: string;
  date_to?: string;
}): Promise<PaginatedResponse<ActivityLog>> {
  const { data } = await apiClient.get("/activities/", { params });
  return data;
}

export async function createActivity(activity: {
  agent_id: string;
  task_id?: string;
  action: string;
  level?: string;
  summary?: string;
  details?: Record<string, unknown>;
}): Promise<ActivityLog> {
  const { data } = await apiClient.post("/activities/", activity);
  return data;
}

export async function getActivitySummary(): Promise<Record<string, number>> {
  const { data } = await apiClient.get("/activities/summary");
  return data;
}
