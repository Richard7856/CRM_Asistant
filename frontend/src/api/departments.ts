import apiClient from "./client";
import type { Agent } from "@/types/agent";
import type { Department, DepartmentTreeNode, CreateDepartment } from "@/types/department";
import type { PaginatedResponse } from "@/types/common";

export async function listDepartments(params?: {
  page?: number;
  size?: number;
}): Promise<PaginatedResponse<Department>> {
  const { data } = await apiClient.get("/departments/", { params });
  return data;
}

export async function getDepartment(id: string): Promise<Department> {
  const { data } = await apiClient.get(`/departments/${id}`);
  return data;
}

export async function createDepartment(dept: CreateDepartment): Promise<Department> {
  const { data } = await apiClient.post("/departments/", dept);
  return data;
}

export async function updateDepartment(id: string, updates: Partial<Department>): Promise<Department> {
  const { data } = await apiClient.patch(`/departments/${id}`, updates);
  return data;
}

export async function getDepartmentTree(): Promise<DepartmentTreeNode[]> {
  const { data } = await apiClient.get("/departments/tree");
  return data;
}

export async function getDepartmentAgents(id: string): Promise<Agent[]> {
  const { data } = await apiClient.get(`/departments/${id}/agents`);
  return data;
}
