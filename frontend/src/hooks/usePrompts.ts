import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listTemplates,
  getTemplate,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  listVersions,
  createVersion,
  activateVersion,
  compareVersions,
  applyTemplate,
} from "@/api/prompts";
import type { CreatePromptTemplate, CreatePromptVersion } from "@/types/prompt";

// ── Templates ──────────────────────────────────────────────

export function useTemplates(params?: {
  category?: string;
  search?: string;
  page?: number;
  size?: number;
}) {
  return useQuery({
    queryKey: ["prompt-templates", params],
    queryFn: () => listTemplates(params),
  });
}

export function useTemplate(id: string | undefined) {
  return useQuery({
    queryKey: ["prompt-template", id],
    queryFn: () => getTemplate(id!),
    enabled: !!id,
  });
}

export function useCreateTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreatePromptTemplate) => createTemplate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompt-templates"] });
    },
  });
}

export function useUpdateTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: Partial<CreatePromptTemplate> }) =>
      updateTemplate(id, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompt-templates"] });
    },
  });
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteTemplate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompt-templates"] });
    },
  });
}

// ── Versions ───────────────────────────────────────────────

export function useVersions(agentId: string | undefined, params?: { page?: number; size?: number }) {
  return useQuery({
    queryKey: ["prompt-versions", agentId, params],
    queryFn: () => listVersions(agentId!, params),
    enabled: !!agentId,
  });
}

export function useCreateVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, data }: { agentId: string; data: CreatePromptVersion }) =>
      createVersion(agentId, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["prompt-versions", variables.agentId] });
    },
  });
}

export function useActivateVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, version }: { agentId: string; version: number }) =>
      activateVersion(agentId, version),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["prompt-versions", variables.agentId] });
    },
  });
}

export function useCompareVersions(agentId: string | undefined, v1: number, v2: number) {
  return useQuery({
    queryKey: ["prompt-compare", agentId, v1, v2],
    queryFn: () => compareVersions(agentId!, v1, v2),
    enabled: !!agentId && v1 > 0 && v2 > 0 && v1 !== v2,
  });
}

export function useApplyTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, templateId }: { agentId: string; templateId: string }) =>
      applyTemplate(agentId, templateId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["prompt-versions", variables.agentId] });
    },
  });
}
