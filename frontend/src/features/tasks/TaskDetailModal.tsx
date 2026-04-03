/**
 * Neumorphic task detail modal — shows full task info and execution result.
 * Floats over a frosted backdrop with soft shadows.
 */

import { useQuery } from "@tanstack/react-query";
import { getTask } from "@/api/tasks";
import { useExecuteTask } from "@/hooks/useTasks";
import StatusBadge from "@/components/common/StatusBadge";
import { TASK_STATUS_COLORS, PRIORITY_COLORS } from "@/lib/constants";
import { formatDateTime, formatMs } from "@/lib/formatters";
import { useToastStore } from "@/stores/toastStore";
import {
  X,
  Play,
  Loader2,
  Clock,
  Zap,
  CheckCircle,
  AlertTriangle,
} from "lucide-react";
import type { Task } from "@/types/task";

interface Props {
  taskId: string;
  onClose: () => void;
}

export default function TaskDetailModal({ taskId, onClose }: Props) {
  const addToast = useToastStore((s) => s.addToast);

  const { data: task, isLoading } = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => getTask(taskId),
    refetchInterval: 3000,
  });

  const executeMutation = useExecuteTask();

  const handleExecute = () => {
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

  const canExecute =
    task &&
    ["assigned", "failed"].includes(task.status) &&
    task.assigned_to !== null;

  const isExecuting = executeMutation.isPending;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center animate-fade-in">
      {/* Frosted backdrop */}
      <div
        className="absolute inset-0 bg-black/20 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal — neumorphic raised surface */}
      <div className="relative neu-flat w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5">
          <h2 className="text-lg font-semibold text-[var(--text-primary)] truncate">
            {task?.title ?? "Cargando..."}
          </h2>
          <button
            onClick={onClose}
            className="neu-sm p-2 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-2 space-y-5">
          {isLoading || !task ? (
            <div className="flex justify-center py-10">
              <div className="neu-pressed w-12 h-12 rounded-full flex items-center justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
              </div>
            </div>
          ) : (
            <>
              {/* Status row */}
              <div className="flex items-center gap-3">
                <StatusBadge
                  status={task.status}
                  colorMap={TASK_STATUS_COLORS}
                />
                <StatusBadge
                  status={task.priority}
                  colorMap={PRIORITY_COLORS}
                />
                {task.started_at && (
                  <span className="text-xs text-[var(--text-muted)] flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatDateTime(task.started_at)}
                  </span>
                )}
              </div>

              {/* Description */}
              {task.description && (
                <div className="neu-pressed p-4">
                  <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
                    Descripcion
                  </h3>
                  <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap">
                    {task.description}
                  </p>
                </div>
              )}

              {/* Execution Result */}
              {task.result && (
                <TaskResultSection result={task.result} status={task.status} />
              )}

              {/* In-progress indicator */}
              {task.status === "in_progress" && !task.result?.output && (
                <div className="neu-pressed p-4 flex items-center gap-3">
                  <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
                  <span className="text-sm text-indigo-500 font-medium">
                    Agente trabajando...
                  </span>
                </div>
              )}

              {/* Metadata */}
              <div className="grid grid-cols-2 gap-4">
                <div className="neu-pressed-sm p-3">
                  <span className="text-[11px] text-[var(--text-muted)] uppercase tracking-wider">
                    Creada
                  </span>
                  <p className="text-sm font-medium text-[var(--text-primary)] mt-1">
                    {formatDateTime(task.created_at)}
                  </p>
                </div>
                {task.completed_at && (
                  <div className="neu-pressed-sm p-3">
                    <span className="text-[11px] text-[var(--text-muted)] uppercase tracking-wider">
                      Completada
                    </span>
                    <p className="text-sm font-medium text-[var(--text-primary)] mt-1">
                      {formatDateTime(task.completed_at)}
                    </p>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-5">
          <button
            onClick={onClose}
            className="neu-sm px-5 py-2.5 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            Cerrar
          </button>
          {canExecute && (
            <button
              onClick={handleExecute}
              disabled={isExecuting}
              className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-xl hover:from-indigo-600 hover:to-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {isExecuting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Ejecutando...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  {task?.status === "failed" ? "Reintentar" : "Ejecutar"}
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Neumorphic result section — inset well with accent color */
function TaskResultSection({
  result,
  status,
}: {
  result: Record<string, unknown>;
  status: string;
}) {
  const isError = status === "failed" || !!result.error;

  return (
    <div className="neu-pressed p-4">
      <div className="flex items-center gap-2 mb-3">
        {isError ? (
          <AlertTriangle className="w-4 h-4 text-red-400" />
        ) : (
          <CheckCircle className="w-4 h-4 text-emerald-400" />
        )}
        <h3
          className={`text-xs font-semibold uppercase tracking-wider ${
            isError ? "text-red-400" : "text-emerald-500"
          }`}
        >
          {isError ? "Error" : "Resultado"}
        </h3>
        {/* Stats badges */}
        <div className="ml-auto flex items-center gap-3">
          {result.elapsed_ms != null && (
            <span className="flex items-center gap-1 text-[11px] text-[var(--text-muted)]">
              <Clock className="w-3 h-3" />
              {formatMs(Number(result.elapsed_ms))}
            </span>
          )}
          {result.usage != null && (
            <span className="flex items-center gap-1 text-[11px] text-[var(--text-muted)]">
              <Zap className="w-3 h-3" />
              {(() => {
                const u = result.usage as Record<string, number>;
                return ((u?.input_tokens ?? 0) + (u?.output_tokens ?? 0)).toLocaleString();
              })()}{" "}
              tokens
            </span>
          )}
        </div>
      </div>

      <div
        className={`text-sm whitespace-pre-wrap leading-relaxed ${
          isError ? "text-red-400" : "text-[var(--text-secondary)]"
        }`}
      >
        {isError
          ? String(result.error ?? "Error desconocido")
          : String(result.output ?? JSON.stringify(result, null, 2))}
      </div>

      {result.model != null && (
        <p className="mt-3 text-[11px] text-[var(--text-muted)]">
          Modelo: {String(result.model)}
        </p>
      )}
    </div>
  );
}
