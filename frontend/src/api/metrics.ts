import apiClient from "./client";
import type { PerformanceMetric, MetricOverview, MetricTrend, MetricSummary } from "@/types/metric";
import type { PaginatedResponse } from "@/types/common";

export async function listMetrics(params?: {
  agent_id?: string;
  department_id?: string;
  period?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  size?: number;
}): Promise<PaginatedResponse<PerformanceMetric>> {
  const { data } = await apiClient.get("/metrics/", { params });
  return data;
}

export async function getMetricOverview(): Promise<MetricOverview> {
  const { data } = await apiClient.get("/metrics/overview");
  return data;
}

export async function getLeaderboard(limit: number = 10): Promise<{ agent_id: string; agent_name: string; success_rate: number }[]> {
  const { data } = await apiClient.get("/metrics/leaderboard", { params: { limit } });
  return data;
}

export async function getAgentTrend(
  agentId: string,
  period: string = "daily",
  limit: number = 30,
): Promise<MetricTrend[]> {
  const { data } = await apiClient.get(`/metrics/agents/${agentId}/trend`, {
    params: { period, limit },
  });
  return data;
}

export async function getMetricsSummary(): Promise<MetricSummary> {
  const { data } = await apiClient.get("/metrics/summary");
  return data;
}
