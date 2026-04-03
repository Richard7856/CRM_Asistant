export type TaskStatus =
  | "pending"
  | "assigned"
  | "in_progress"
  | "review"
  | "completed"
  | "failed"
  | "cancelled";

export type TaskPriority = "low" | "medium" | "high" | "critical";

export interface Task {
  id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  assigned_to: string | null;
  created_by: string | null;
  department_id: string | null;
  parent_task_id: string | null;
  due_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  result: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  // Joined
  assignee_name?: string;
  department_name?: string;
}

export interface CreateTask {
  title: string;
  description?: string;
  priority?: TaskPriority;
  assigned_to?: string;
  department_id?: string;
  parent_task_id?: string;
  due_at?: string;
}
