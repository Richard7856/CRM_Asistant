export type InteractionChannel =
  | "api_call"
  | "message_queue"
  | "webhook"
  | "internal_bus"
  | "direct";

export interface AgentInteraction {
  id: string;
  from_agent_id: string;
  to_agent_id: string;
  channel: InteractionChannel;
  task_id: string | null;
  payload_summary: string | null;
  latency_ms: number | null;
  success: boolean;
  occurred_at: string;
  // Joined
  from_agent_name?: string;
  to_agent_name?: string;
}

export interface InteractionGraphNode {
  id: string;
  name: string;
  department: string;
}

export interface InteractionGraphEdge {
  source: string;
  target: string;
  weight: number;
}

export interface InteractionGraphData {
  nodes: InteractionGraphNode[];
  edges: InteractionGraphEdge[];
}
