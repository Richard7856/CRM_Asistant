import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listAgents, getAgent, listRoles, createInternalAgent, registerExternalAgent } from "@/api/agents";
import type { CreateInternalAgent, RegisterExternalAgent } from "@/types/agent";

export function useAgents(params?: {
  page?: number;
  size?: number;
  department_id?: string;
  status?: string;
  origin?: string;
}) {
  return useQuery({
    queryKey: ["agents", params],
    queryFn: () => listAgents(params),
  });
}

export function useAgent(id: string | undefined) {
  return useQuery({
    queryKey: ["agent", id],
    queryFn: () => getAgent(id!),
    enabled: !!id,
  });
}

export function useRoles() {
  return useQuery({
    queryKey: ["roles"],
    queryFn: listRoles,
  });
}

export function useCreateInternalAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateInternalAgent) => createInternalAgent(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useRegisterExternalAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: RegisterExternalAgent) => registerExternalAgent(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}
