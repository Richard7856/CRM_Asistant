import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listTasks, createTask, executeTask } from "@/api/tasks";
import type { CreateTask } from "@/types/task";

export function useTasks(params?: {
  page?: number;
  size?: number;
  status?: string;
  priority?: string;
  assigned_to?: string;
  department_id?: string;
}) {
  return useQuery({
    queryKey: ["tasks", params],
    queryFn: () => listTasks(params),
  });
}

export function useCreateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (task: CreateTask) => createTask(task),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

/** Trigger task execution — calls Claude API or dispatches to external agent */
export function useExecuteTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (taskId: string) => executeTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["activities"] });
      queryClient.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
}
