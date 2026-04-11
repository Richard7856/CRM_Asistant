import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listTasks } from "@/api/tasks";
import { useExecuteTask } from "@/hooks/useTasks";
import { useToastStore } from "@/stores/toastStore";
import StatusBadge from "@/components/common/StatusBadge";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import { TASK_STATUS_COLORS, PRIORITY_COLORS } from "@/lib/constants";
import { formatRelative } from "@/lib/formatters";
import { Play, Loader2, Eye, Plus, LayoutGrid, Table } from "lucide-react";
import type { Task } from "@/types/task";

const KANBAN_COLUMNS = [
  "pending",
  "assigned",
  "in_progress",
  "completed",
  "failed",
] as const;

export default function TaskListPage() {
  const navigate = useNavigate();
  const [view, setView] = useState<"kanban" | "table">("kanban");
  const addToast = useToastStore((s) => s.addToast);

  const { data, isLoading } = useQuery({
    queryKey: ["tasks", { page: 1, size: 100 }],
    queryFn: () => listTasks({ page: 1, size: 100 }),
  });

  const executeMutation = useExecuteTask();

  const handleExecute = (e: React.MouseEvent, taskId: string) => {
    e.stopPropagation();
    executeMutation.mutate(taskId, {
      onSuccess: (result: Task) => {
        addToast({
          type: result.status === "completed" ? "success" : "error",
          title:
            result.status === "completed"
              ? "Tarea completada"
              : "Tarea fallida",
          message: result.title,
        });
      },
      onError: () => {
        addToast({
          type: "error",
          title: "Error al ejecutar",
          message: "No se pudo ejecutar la tarea",
        });
      },
    });
  };

  if (isLoading) return <LoadingSpinner />;

  const tasks = data?.items ?? [];

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Tareas</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("/tasks/new")}
            className="neu-sm flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-xl hover:from-indigo-600 hover:to-indigo-700 transition-all"
          >
            <Plus className="w-4 h-4" />
            Nueva Tarea
          </button>
          <div className="neu-pressed-sm flex gap-1 p-1">
            <button
              onClick={() => setView("kanban")}
              className={`p-2 rounded-lg transition-all duration-200 ${
                view === "kanban"
                  ? "neu-sm text-indigo-500"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView("table")}
              className={`p-2 rounded-lg transition-all duration-200 ${
                view === "table"
                  ? "neu-sm text-indigo-500"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              <Table className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {view === "kanban" ? (
        <div className="flex gap-4 overflow-x-auto pb-4">
          {KANBAN_COLUMNS.map((col) => {
            const colTasks = tasks.filter((t) => t.status === col);
            return (
              <div key={col} className="min-w-[280px] flex-shrink-0">
                <div className="flex items-center gap-2 mb-3 px-1">
                  <StatusBadge status={col} colorMap={TASK_STATUS_COLORS} />
                  <span className="text-xs text-[var(--text-muted)] font-mono">
                    {colTasks.length}
                  </span>
                </div>
                <div className="space-y-3">
                  {colTasks.map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      isExecuting={
                        executeMutation.isPending &&
                        executeMutation.variables === task.id
                      }
                      onExecute={handleExecute}
                      onClick={() => navigate(`/tasks/${task.id}`)}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="neu-flat overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--text-muted)]">
                <th className="text-left px-5 py-4 text-xs font-medium uppercase tracking-wider">
                  Titulo
                </th>
                <th className="text-left px-5 py-4 text-xs font-medium uppercase tracking-wider">
                  Estado
                </th>
                <th className="text-left px-5 py-4 text-xs font-medium uppercase tracking-wider">
                  Prioridad
                </th>
                <th className="text-left px-5 py-4 text-xs font-medium uppercase tracking-wider">
                  Asignado a
                </th>
                <th className="text-left px-5 py-4 text-xs font-medium uppercase tracking-wider">
                  Actualizado
                </th>
                <th className="text-right px-5 py-4 text-xs font-medium uppercase tracking-wider">
                  Acciones
                </th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => {
                const canExec =
                  ["assigned", "failed"].includes(task.status) &&
                  task.assigned_to !== null;
                const isExec =
                  executeMutation.isPending &&
                  executeMutation.variables === task.id;
                return (
                  <tr
                    key={task.id}
                    className="hover:bg-white/30 cursor-pointer transition-colors"
                    onClick={() => navigate(`/tasks/${task.id}`)}
                  >
                    <td className="px-5 py-3.5 font-medium text-[var(--text-primary)]">
                      {task.title}
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge
                        status={task.status}
                        colorMap={TASK_STATUS_COLORS}
                      />
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge
                        status={task.priority}
                        colorMap={PRIORITY_COLORS}
                      />
                    </td>
                    <td className="px-5 py-3.5 text-[var(--text-secondary)]">
                      {task.assignee_name ?? "--"}
                    </td>
                    <td className="px-5 py-3.5 text-xs text-[var(--text-muted)]">
                      {formatRelative(task.updated_at)}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/tasks/${task.id}`);
                          }}
                          className="p-2 rounded-lg neu-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                          title="Ver detalle"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                        {canExec && (
                          <button
                            onClick={(e) => handleExecute(e, task.id)}
                            disabled={isExec}
                            className="p-2 rounded-lg neu-sm text-indigo-500 hover:text-indigo-600 disabled:opacity-50 transition-colors"
                            title={
                              task.status === "failed"
                                ? "Reintentar"
                                : "Ejecutar"
                            }
                          >
                            {isExec ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Play className="w-3.5 h-3.5" />
                            )}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

    </div>
  );
}

function TaskCard({
  task,
  isExecuting,
  onExecute,
  onClick,
}: {
  task: Task;
  isExecuting: boolean;
  onExecute: (e: React.MouseEvent, id: string) => void;
  onClick: () => void;
}) {
  const canExecute =
    ["assigned", "failed"].includes(task.status) &&
    task.assigned_to !== null;

  return (
    <div
      onClick={onClick}
      className="neu-flat p-4 cursor-pointer group hover:shadow-none transition-shadow duration-200"
    >
      <p className="text-sm font-medium text-[var(--text-primary)]">{task.title}</p>
      <div className="flex items-center justify-between mt-3">
        <StatusBadge status={task.priority} colorMap={PRIORITY_COLORS} />
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-[var(--text-muted)]">
            {task.assignee_name ?? "Sin asignar"}
          </span>
          {canExecute && (
            <button
              onClick={(e) => onExecute(e, task.id)}
              disabled={isExecuting}
              className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg neu-sm text-indigo-500 disabled:opacity-50"
              title={task.status === "failed" ? "Reintentar" : "Ejecutar"}
            >
              {isExecuting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5" />
              )}
            </button>
          )}
        </div>
      </div>
      {task.status === "completed" && task.result?.output != null && (
        <p className="mt-2 text-xs text-[var(--text-muted)] line-clamp-2">
          {String(task.result.output)}
        </p>
      )}
      {task.status === "failed" && task.result?.error != null && (
        <p className="mt-2 text-xs text-red-400 line-clamp-1">
          {String(task.result.error)}
        </p>
      )}
    </div>
  );
}
