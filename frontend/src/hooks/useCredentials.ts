import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listCredentials,
  createCredential,
  updateCredential,
  deleteCredential,
  listAgentCredentials,
} from "@/api/credentials";
import type { CreateCredential, UpdateCredential } from "@/types/credential";

export function useCredentials(params?: {
  page?: number;
  size?: number;
  service_name?: string;
  agent_id?: string;
  is_active?: boolean;
}) {
  return useQuery({
    queryKey: ["credentials", params],
    queryFn: () => listCredentials(params),
  });
}

export function useAgentCredentials(agentId: string | undefined) {
  return useQuery({
    queryKey: ["credentials", "agent", agentId],
    queryFn: () => listAgentCredentials(agentId!),
    enabled: !!agentId,
  });
}

export function useCreateCredential() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateCredential) => createCredential(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["credentials"] });
    },
  });
}

export function useUpdateCredential() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateCredential }) =>
      updateCredential(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["credentials"] });
    },
  });
}

export function useDeleteCredential() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteCredential(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["credentials"] });
    },
  });
}
