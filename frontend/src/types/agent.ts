export type AgentOrigin = "internal" | "external";
export type AgentStatus =
  | "active"
  | "idle"
  | "busy"
  | "error"
  | "offline"
  | "maintenance";
export type RoleLevel = "agent" | "supervisor" | "manager" | "admin";

export interface Role {
  id: string;
  name: string;
  level: RoleLevel;
  description: string | null;
}

export interface Agent {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  origin: AgentOrigin;
  status: AgentStatus;
  role_id: string;
  department_id: string;
  supervisor_id: string | null;
  avatar_url: string | null;
  capabilities: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  last_heartbeat_at: string | null;
  // Lifecycle fields
  last_task_completed_at: string | null;
  total_tasks_completed: number;
  created_by_agent_id: string | null;
  creation_reason: string | null;
  // Joined fields
  role_name?: string;
  department_name?: string;
  supervisor_name?: string;
}

export interface AgentDetail extends Agent {
  integration?: AgentIntegration;
  definition?: AgentDefinition;
}

export interface AgentIntegration {
  id: string;
  integration_type: string;
  platform: string | null;
  endpoint_url: string | null;
  polling_interval_seconds: number;
  config: Record<string, unknown>;
  is_active: boolean;
  last_sync_at: string | null;
}

export interface AgentDefinition {
  id: string;
  system_prompt: string | null;
  model_provider: string | null;
  model_name: string | null;
  temperature: number;
  max_tokens: number;
  tools: unknown[];
  knowledge_base: Record<string, unknown>;
  config: Record<string, unknown>;
  version: number;
}

export interface CreateInternalAgent {
  name: string;
  description?: string;
  role_id: string;
  department_id: string;
  supervisor_id?: string;
  capabilities?: string[];
  avatar_url?: string;
  system_prompt?: string;
  model_provider?: string;
  model_name?: string;
  temperature?: number;
  max_tokens?: number;
  tools?: unknown[];
}

export interface RegisterExternalAgent {
  name: string;
  description?: string;
  role_id: string;
  department_id: string;
  supervisor_id?: string;
  capabilities?: string[];
  integration_type: string;
  platform?: string;
  endpoint_url?: string;
  polling_interval_seconds?: number;
  integration_config?: Record<string, unknown>;
}
