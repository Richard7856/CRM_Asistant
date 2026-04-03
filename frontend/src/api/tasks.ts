import apiClient from "./client";
import type { Task, CreateTask } from "@/types/task";
import type { PaginatedResponse } from "@/types/common";

export async function listTasks(params?: {
  page?: number;
  size?: number;
  status?: string;
  priority?: string;
  assigned_to?: string;
  department_id?: string;
}): Promise<PaginatedResponse<Task>> {
  const { data } = await apiClient.get("/tasks/", { params });
  return data;
}

export async function getTask(id: string): Promise<Task> {
  const { data } = await apiClient.get(`/tasks/${id}`);
  return data;
}

export async function createTask(task: CreateTask): Promise<Task> {
  const { data } = await apiClient.post("/tasks/", task);
  return data;
}

export async function updateTask(id: string, updates: Partial<Task>): Promise<Task> {
  const { data } = await apiClient.patch(`/tasks/${id}`, updates);
  return data;
}

export async function assignTask(id: string, agentId: string): Promise<Task> {
  const { data } = await apiClient.post(`/tasks/${id}/assign`, { agent_id: agentId });
  return data;
}

export async function getSubtasks(id: string): Promise<Task[]> {
  const { data } = await apiClient.get(`/tasks/${id}/subtasks`);
  return data;
}

/** Trigger agent execution — calls Claude API for internal or dispatches for external agents */
export async function executeTask(id: string): Promise<Task> {
  const { data } = await apiClient.post(`/tasks/${id}/execute`);
  return data;
}
