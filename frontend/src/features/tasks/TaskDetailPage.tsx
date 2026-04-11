/**
 * Full-page task detail — shows delegation tree, KB sources, and aggregated output.
 *
 * Replaces the basic modal for tasks that have rich result data
 * (delegation subtasks, KB citations, token usage).
 * Neumorphic design consistent with the rest of the app.
 */

import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getTask, getSubtasks } from "@/api/tasks";
import { useExecuteTask } from "@/hooks/useTasks";
import StatusBadge from "@/components/common/StatusBadge";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import { TASK_STATUS_COLORS, PRIORITY_COLORS } from "@/lib/constants";
import { formatDateTime, formatMs, formatNumber } from "@/lib/formatters";
import { useToastStore } from "@/stores/toastStore";
import {
  ArrowLeft,
  Play,
  Loader2,
  Clock,
  Zap,
  CheckCircle,
  AlertTriangle,
  GitBranch,
  BookOpen,
  Users,
  ChevronDown,
  ChevronRight,
  Bot,
  FileText,
} from "lucide-react";
import { useState } from "react";
import type { Task } from "@/types/task";

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const addToast = useToastStore((s) => s.addToast);

  const { data: task, isLoading } = useQuery({
    queryKey: ["task", id],
    queryFn: () => getTask(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Poll while in progress, stop once terminal
      return status === "in_progress" || status === "assigned" ? 3000 : false;
    },
  });

  const { data: subtasks } = useQuery({
    queryKey: ["subtasks", id],
    queryFn: () => getSubtasks(id!),
    enabled: !!id && !!task?.result?.delegation,
  });

  const executeMutation = useExecuteTask();

  const handleExecute = () => {
    executeMutation.mutate(id!, {
      onSuccess: () => {
        addToast({ type: "success", title: "Tarea lanzada", message: "Ejecución iniciada en background" });
      },
      onError: () => {
        addToast({ type: "error", title: "Error", message: "No se pudo ejecutar la tarea" });
      },
    });
  };

  if (isLoading || !task) return <LoadingSpinner />;

  const result = task.result as Record<string, unknown> | null;
  const delegation = result?.delegation as Record<string, number> | undefined;
  const subtaskOutputs = result?.subtask_outputs as Array<{ agent: string; title: string; status: string }> | undefined;
  const kbSources = (result?.kb_sources ?? []) as Array<{ document_title: string; document_id: string; chunk_index: number; relevance: number }>;
  const usage = result?.usage as { input_tokens: number; output_tokens: number } | undefined;
  const canExecute = ["assigned", "failed"].includes(task.status) && task.assigned_to !== null;
  const isDelegation = !!delegation;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <button
          onClick={() => navigate(-1)}
          className="neu-sm p-2.5 mt-0.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-[var(--text-primary)] leading-tight">
            {task.title}
          </h1>
          <div className="flex items-center gap-3 mt-2">
            <StatusBadge status={task.status} colorMap={TASK_STATUS_COLORS} />
            <StatusBadge status={task.priority} colorMap={PRIORITY_COLORS} />
            {isDelegation && (
              <span className="flex items-center gap-1 text-xs font-medium text-indigo-500 bg-indigo-50 px-2 py-0.5 rounded-full">
                <GitBranch className="w-3 h-3" />
                Delegación
              </span>
            )}
            {task.started_at && (
              <span className="text-xs text-[var(--text-muted)] flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {formatDateTime(task.started_at)}
              </span>
            )}
          </div>
        </div>
        {canExecute && (
          <button
            onClick={handleExecute}
            disabled={executeMutation.isPending}
            className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-xl hover:from-indigo-600 hover:to-indigo-700 disabled:opacity-50 transition-all"
          >
            {executeMutation.isPending ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Ejecutando...</>
            ) : (
              <><Play className="w-4 h-4" /> {task.status === "failed" ? "Reintentar" : "Ejecutar"}</>
            )}
          </button>
        )}
      </div>

      {/* Description */}
      {task.description && (
        <div className="neu-pressed p-5">
          <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
            Descripción
          </h3>
          <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap">
            {task.description}
          </p>
        </div>
      )}

      {/* In-progress indicator */}
      {task.status === "in_progress" && !result?.output && (
        <div className="neu-pressed p-5 flex items-center gap-3">
          <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
          <div>
            <span className="text-sm text-indigo-500 font-medium">
              {isDelegation ? "Supervisor delegando subtareas..." : "Agente trabajando..."}
            </span>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              El resultado aparecerá aquí automáticamente
            </p>
          </div>
        </div>
      )}

      {/* Stats bar — only when completed */}
      {result && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {result.elapsed_ms != null && (
            <StatCard icon={Clock} label="Tiempo total" value={formatMs(Number(result.elapsed_ms))} />
          )}
          {usage && (
            <StatCard icon={Zap} label="Tokens" value={formatNumber(usage.input_tokens + usage.output_tokens)} />
          )}
          {delegation && (
            <StatCard icon={Users} label="Subtareas" value={`${delegation.subtasks_completed}/${delegation.subtasks_created}`} />
          )}
          {kbSources.length > 0 && (
            <StatCard icon={BookOpen} label="Fuentes KB" value={String(kbSources.length)} />
          )}
        </div>
      )}

      {/* Delegation tree */}
      {isDelegation && subtaskOutputs && (
        <DelegationSection subtaskOutputs={subtaskOutputs} subtasks={subtasks ?? []} />
      )}

      {/* KB Sources */}
      {kbSources.length > 0 && (
        <KBSourcesSection sources={kbSources} />
      )}

      {/* Main output */}
      {result && (
        <div className="neu-pressed p-5">
          <div className="flex items-center gap-2 mb-3">
            {task.status === "failed" ? (
              <AlertTriangle className="w-4 h-4 text-red-400" />
            ) : (
              <CheckCircle className="w-4 h-4 text-emerald-400" />
            )}
            <h3 className={`text-xs font-semibold uppercase tracking-wider ${
              task.status === "failed" ? "text-red-400" : "text-emerald-500"
            }`}>
              {task.status === "failed" ? "Error" : isDelegation ? "Entregable Final (Supervisor)" : "Resultado"}
            </h3>
            {!!result.model && (
              <span className="ml-auto text-[11px] text-[var(--text-muted)]">
                {String(result.model)}
              </span>
            )}
          </div>
          <div className={`text-sm whitespace-pre-wrap leading-relaxed ${
            task.status === "failed" ? "text-red-400" : "text-[var(--text-secondary)]"
          }`}>
            {task.status === "failed"
              ? String(result.error ?? "Error desconocido")
              : String(result.output ?? "")}
          </div>
        </div>
      )}

      {/* Metadata footer */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetaCard label="Creada" value={formatDateTime(task.created_at)} />
        {task.completed_at && <MetaCard label="Completada" value={formatDateTime(task.completed_at)} />}
        {task.assignee_name && <MetaCard label="Asignado a" value={task.assignee_name} />}
        {task.department_id && <MetaCard label="Departamento" value={task.department_name ?? task.department_id} />}
      </div>
    </div>
  );
}

// ── Stat Card ─────────────────────────────────────────────

function StatCard({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string }) {
  return (
    <div className="neu-flat p-4 rounded-xl">
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-3.5 h-3.5 text-indigo-400" />
        <span className="text-[11px] text-[var(--text-muted)] uppercase tracking-wider">{label}</span>
      </div>
      <p className="text-lg font-bold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

function MetaCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="neu-pressed-sm p-3">
      <span className="text-[11px] text-[var(--text-muted)] uppercase tracking-wider">{label}</span>
      <p className="text-sm font-medium text-[var(--text-primary)] mt-1">{value}</p>
    </div>
  );
}

// ── Delegation Section ────────────────────────────────────

function DelegationSection({
  subtaskOutputs,
  subtasks,
}: {
  subtaskOutputs: Array<{ agent: string; title: string; status: string }>;
  subtasks: Task[];
}) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  return (
    <div className="neu-flat p-5 rounded-xl">
      <div className="flex items-center gap-2 mb-4">
        <GitBranch className="w-4 h-4 text-indigo-400" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-indigo-500">
          Subtareas Delegadas
        </h3>
      </div>

      <div className="space-y-2">
        {subtaskOutputs.map((st, idx) => {
          const isExpanded = expandedIdx === idx;
          const matchedSubtask = subtasks.find((s) => s.title === st.title);
          const stResult = matchedSubtask?.result as Record<string, unknown> | null;

          return (
            <div key={idx} className="neu-pressed rounded-lg overflow-hidden">
              <button
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                className="w-full flex items-center gap-3 p-3 text-left hover:bg-black/[0.02] transition-colors"
              >
                {isExpanded ? (
                  <ChevronDown className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                )}
                {st.status === "completed" ? (
                  <CheckCircle className="w-4 h-4 text-emerald-400" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-red-400" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                    {st.title}
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    <Bot className="w-3 h-3 inline mr-1" />
                    {st.agent}
                  </p>
                </div>
                {stResult?.elapsed_ms != null && (
                  <span className="text-[11px] text-[var(--text-muted)] flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatMs(Number(stResult.elapsed_ms))}
                  </span>
                )}
              </button>

              {isExpanded && !!stResult?.output && (
                <div className="px-4 pb-4 pt-1">
                  {/* Subtask KB sources */}
                  {Array.isArray(stResult.kb_sources) && (stResult.kb_sources as Array<Record<string, unknown>>).length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-2">
                      {(stResult.kb_sources as Array<{ document_title: string }>).map((src, i) => (
                        <span key={i} className="text-[10px] bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded flex items-center gap-0.5">
                          <FileText className="w-2.5 h-2.5" />
                          {src.document_title}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto bg-[var(--neu-bg)] rounded-lg p-3">
                    {String(stResult.output)}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── KB Sources Section ────────────────────────────────────

function KBSourcesSection({
  sources,
}: {
  sources: Array<{ document_title: string; document_id: string; chunk_index: number; relevance: number }>;
}) {
  // Deduplicate by document_title
  const uniqueDocs = new Map<string, { title: string; chunks: number; maxRelevance: number }>();
  for (const src of sources) {
    const existing = uniqueDocs.get(src.document_title);
    if (existing) {
      existing.chunks++;
      existing.maxRelevance = Math.max(existing.maxRelevance, src.relevance);
    } else {
      uniqueDocs.set(src.document_title, { title: src.document_title, chunks: 1, maxRelevance: src.relevance });
    }
  }

  return (
    <div className="neu-flat p-5 rounded-xl">
      <div className="flex items-center gap-2 mb-3">
        <BookOpen className="w-4 h-4 text-amber-500" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-amber-600">
          Fuentes del Knowledge Base
        </h3>
      </div>
      <div className="flex flex-wrap gap-2">
        {Array.from(uniqueDocs.values()).map((doc) => (
          <div
            key={doc.title}
            className="flex items-center gap-2 neu-pressed-sm px-3 py-2 rounded-lg"
          >
            <FileText className="w-3.5 h-3.5 text-amber-500" />
            <div>
              <p className="text-xs font-medium text-[var(--text-primary)]">{doc.title}</p>
              <p className="text-[10px] text-[var(--text-muted)]">
                {doc.chunks} {doc.chunks === 1 ? "sección" : "secciones"} consultadas
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
