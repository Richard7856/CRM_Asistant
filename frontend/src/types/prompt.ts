export interface PromptVersion {
  id: string;
  agent_id: string;
  version: number;
  system_prompt: string;
  model_provider: string | null;
  model_name: string | null;
  temperature: number;
  max_tokens: number;
  tools: any[];
  change_notes: string | null;
  created_by: string | null;
  is_active: boolean;
  performance_score: number | null;
  created_at: string;
}

export interface PromptTemplate {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  category: string;
  system_prompt: string;
  model_provider: string | null;
  model_name: string | null;
  temperature: number;
  max_tokens: number;
  tools: any[];
  tags: string[];
  usage_count: number;
  created_at: string;
  updated_at: string;
}

export interface CreatePromptVersion {
  system_prompt: string;
  model_provider?: string;
  model_name?: string;
  temperature?: number;
  max_tokens?: number;
  tools?: any[];
  change_notes?: string;
  created_by?: string;
}

export interface CreatePromptTemplate {
  name: string;
  description?: string;
  category: string;
  system_prompt: string;
  model_provider?: string;
  model_name?: string;
  temperature?: number;
  max_tokens?: number;
  tools?: any[];
  tags?: string[];
}

export interface PromptDiff {
  field: string;
  old_value: string | null;
  new_value: string | null;
}

export interface PromptCompareResponse {
  version_a: number;
  version_b: number;
  diffs: PromptDiff[];
}
