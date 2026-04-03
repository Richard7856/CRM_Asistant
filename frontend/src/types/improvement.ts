import type { TaskPriority } from "./task";

export type ImprovementStatus =
  | "identified"
  | "proposed"
  | "approved"
  | "in_progress"
  | "implemented"
  | "dismissed";

export interface ImprovementPoint {
  id: string;
  agent_id: string;
  identified_by: string | null;
  category: string;
  title: string;
  description: string;
  evidence: Record<string, unknown>;
  status: ImprovementStatus;
  priority: TaskPriority;
  resolution: string | null;
  created_at: string;
  updated_at: string;
  // Joined
  agent_name?: string;
}

export interface CreateImprovement {
  agent_id: string;
  identified_by?: string;
  category: string;
  title: string;
  description: string;
  evidence?: Record<string, unknown>;
  priority?: TaskPriority;
}
