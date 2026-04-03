export type LogLevel = "debug" | "info" | "warning" | "error" | "critical";

export interface ActivityLog {
  id: string;
  agent_id: string;
  task_id: string | null;
  action: string;
  level: LogLevel;
  summary: string | null;
  details: Record<string, unknown>;
  occurred_at: string;
  // Joined
  agent_name?: string;
}
