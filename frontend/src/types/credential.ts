export type CredentialType =
  | "api_key"
  | "oauth_token"
  | "bearer_token"
  | "basic_auth"
  | "custom";

export interface Credential {
  id: string;
  name: string;
  credential_type: CredentialType;
  service_name: string;
  agent_id: string | null;
  agent_name: string | null;
  is_active: boolean;
  secret_preview: string;
  notes: string | null;
  organization_id: string;
  created_at: string;
  updated_at: string;
}

export interface CreateCredential {
  name: string;
  credential_type: CredentialType;
  secret_value: string;
  service_name: string;
  agent_id?: string | null;
  notes?: string;
}

export interface UpdateCredential {
  name?: string;
  credential_type?: CredentialType;
  secret_value?: string;
  service_name?: string;
  agent_id?: string | null;
  is_active?: boolean;
  notes?: string;
}
