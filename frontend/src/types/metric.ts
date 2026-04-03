export type MetricPeriod = "hourly" | "daily" | "weekly" | "monthly";

export interface PerformanceMetric {
  id: string;
  agent_id: string;
  period: MetricPeriod;
  period_start: string;
  period_end: string;
  tasks_completed: number;
  tasks_failed: number;
  avg_response_ms: number | null;
  success_rate: number | null;
  uptime_pct: number | null;
  token_usage: number;
  cost_usd: number;
  custom_kpis: Record<string, unknown>;
}

export interface MetricOverview {
  total_agents: number;
  active_agents: number;
  tasks_completed_today: number;
  overall_success_rate: number;
  avg_response_ms: number;
  total_cost_today: number;
}

export interface MetricTrend {
  period_start: string;
  success_rate: number;
  tasks_completed: number;
  tasks_failed: number;
  cost_usd: number;
  avg_response_ms: number;
}

export interface MetricSummary {
  total_tasks_completed: number;
  total_tasks_failed: number;
  avg_success_rate: number | null;
  avg_response_ms: number | null;
  total_cost_usd: number;
  total_token_usage: number;
  agents_measured: number;
  agents_by_status: Record<string, number>;
  tasks_by_status: Record<string, number>;
  daily_tasks: { date: string; completed: number; failed: number }[];
  top_agents: { agent_id: string; agent_name: string; tasks_completed: number; success_rate: number; cost_usd: number }[];
}
