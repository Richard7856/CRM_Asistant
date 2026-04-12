/**
 * AgentLifecycleCard — shows agent provenance and activity stats.
 *
 * Displayed in the Overview tab of AgentDetailPage.
 * Shows: who created it (human or agent), creation reason,
 * last task completed, total tasks, and days idle.
 */

import { Link } from "react-router-dom";
import { Bot, User, Clock, CheckCircle2, AlertTriangle } from "lucide-react";
import { formatRelative } from "@/lib/formatters";
import type { AgentDetail } from "@/types/agent";

interface Props {
  agent: AgentDetail;
}

export default function AgentLifecycleCard({ agent }: Props) {
  const wasAutonomous = !!agent.created_by_agent_id;
  const daysIdle = calculateDaysIdle(agent);
  const isIdle = daysIdle !== null && daysIdle > 7;

  return (
    <div className="neu-flat p-5 space-y-4">
      <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
        Ciclo de Vida
      </h2>

      <div className="space-y-3">
        {/* Creation provenance */}
        <div className="flex items-start gap-3">
          <div className={`p-1.5 rounded-lg ${wasAutonomous ? "bg-indigo-500/10" : "bg-[var(--neu-dark)]/10"}`}>
            {wasAutonomous ? (
              <Bot className="w-4 h-4 text-indigo-500" />
            ) : (
              <User className="w-4 h-4 text-[var(--text-muted)]" />
            )}
          </div>
          <div>
            <p className="text-sm text-[var(--text-primary)]">
              {wasAutonomous ? "Creado por agente" : "Creado manualmente"}
            </p>
            {wasAutonomous && (
              <Link
                to={`/agents/${agent.created_by_agent_id}`}
                className="text-xs text-indigo-500 hover:text-indigo-600"
              >
                Ver agente creador
              </Link>
            )}
          </div>
        </div>

        {/* Creation reason */}
        {agent.creation_reason && (
          <div className="neu-pressed-sm px-3 py-2 rounded-lg">
            <p className="text-xs text-[var(--text-muted)] mb-0.5">Razon de creacion</p>
            <p className="text-sm text-[var(--text-secondary)]">{agent.creation_reason}</p>
          </div>
        )}

        {/* Task stats */}
        <div className="flex items-center gap-3">
          <div className="p-1.5 rounded-lg bg-emerald-500/10">
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          </div>
          <div>
            <p className="text-sm text-[var(--text-primary)]">
              {agent.total_tasks_completed}{" "}
              {agent.total_tasks_completed === 1 ? "tarea completada" : "tareas completadas"}
            </p>
            <p className="text-xs text-[var(--text-muted)]">
              {agent.last_task_completed_at
                ? `Ultima: ${formatRelative(agent.last_task_completed_at)}`
                : "Ninguna tarea completada"}
            </p>
          </div>
        </div>

        {/* Idle warning */}
        {isIdle && (
          <div className="flex items-center gap-3 bg-amber-500/5 rounded-lg px-3 py-2">
            <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />
            <p className="text-sm text-amber-600">
              Inactivo hace {daysIdle} dias
              {wasAutonomous && " — considere desactivar"}
            </p>
          </div>
        )}

        {/* Days since last activity */}
        {daysIdle !== null && !isIdle && (
          <div className="flex items-center gap-3">
            <div className="p-1.5 rounded-lg bg-[var(--neu-dark)]/10">
              <Clock className="w-4 h-4 text-[var(--text-muted)]" />
            </div>
            <p className="text-sm text-[var(--text-secondary)]">
              {daysIdle === 0
                ? "Activo hoy"
                : `Ultima actividad hace ${daysIdle} ${daysIdle === 1 ? "dia" : "dias"}`}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function calculateDaysIdle(agent: AgentDetail): number | null {
  const lastActive = agent.last_task_completed_at || agent.last_heartbeat_at;
  if (!lastActive) return null;
  const diff = Date.now() - new Date(lastActive).getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}
