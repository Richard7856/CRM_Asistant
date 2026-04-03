export interface Department {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  parent_id: string | null;
  head_agent_id: string | null;
  created_at: string;
  updated_at: string;
  agent_count?: number;
}

export interface DepartmentTreeNode extends Department {
  children: DepartmentTreeNode[];
}

export interface CreateDepartment {
  name: string;
  description?: string;
  parent_id?: string;
}
