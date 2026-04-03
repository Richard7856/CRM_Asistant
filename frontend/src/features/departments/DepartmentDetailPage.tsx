import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getDepartment, getDepartmentAgents } from "@/api/departments";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import StatusBadge from "@/components/common/StatusBadge";
import EmptyState from "@/components/common/EmptyState";
import { formatDateTime } from "@/lib/formatters";
import { ArrowLeft, Users, Calendar } from "lucide-react";

export default function DepartmentDetailPage() {
  const { id } = useParams<{ id: string }>();

  const { data: dept, isLoading } = useQuery({
    queryKey: ["department", id],
    queryFn: () => getDepartment(id!),
    enabled: !!id,
  });

  const { data: agents, isLoading: agentsLoading } = useQuery({
    queryKey: ["department", id, "agents"],
    queryFn: () => getDepartmentAgents(id!),
    enabled: !!id,
  });

  if (isLoading || !dept) return <LoadingSpinner />;

  const headAgent = agents?.find((a) => a.id === dept.head_agent_id);

  return (
    <div className="space-y-6">
      <Link
        to="/departments"
        className="inline-flex items-center gap-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Departamentos
      </Link>

      {/* Header */}
      <div className="neu-flat p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="neu-pressed w-14 h-14 rounded-2xl flex items-center justify-center text-lg font-bold text-indigo-500">
              {dept.name.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <h1 className="text-xl font-semibold text-[var(--text-primary)]">
                {dept.name}
              </h1>
              <div className="mt-2 flex items-center gap-3 text-sm text-[var(--text-muted)]">
                <span className="inline-flex items-center gap-1">
                  <Users className="w-3.5 h-3.5" />
                  {agents?.length ?? dept.agent_count ?? 0} agentes
                </span>
                <span className="inline-flex items-center gap-1">
                  <Calendar className="w-3.5 h-3.5" />
                  {formatDateTime(dept.created_at)}
                </span>
              </div>
            </div>
          </div>
        </div>
        {dept.description && (
          <p className="mt-4 text-sm text-[var(--text-secondary)]">
            {dept.description}
          </p>
        )}
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="neu-flat p-5">
          <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
            Jefe de Departamento
          </p>
          {headAgent ? (
            <Link
              to={`/agents/${headAgent.id}`}
              className="flex items-center gap-3 group"
            >
              <div className="neu-pressed w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold text-indigo-500">
                {headAgent.name.slice(0, 2).toUpperCase()}
              </div>
              <div>
                <span className="text-sm font-medium text-indigo-500 group-hover:text-indigo-600 transition-colors">
                  {headAgent.name}
                </span>
                {headAgent.role_name && (
                  <p className="text-xs text-[var(--text-muted)]">{headAgent.role_name}</p>
                )}
              </div>
            </Link>
          ) : (
            <p className="text-sm text-[var(--text-muted)]">Sin asignar</p>
          )}
        </div>

        <div className="neu-flat p-5">
          <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
            Agentes Activos
          </p>
          <p className="text-2xl font-bold text-emerald-500">
            {agents?.filter((a) => a.status === "active").length ?? 0}
          </p>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            de {agents?.length ?? 0} total
          </p>
        </div>

        <div className="neu-flat p-5">
          <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
            Estado del Equipo
          </p>
          <div className="flex flex-wrap gap-2 mt-1">
            {["active", "idle", "busy", "error", "offline"].map((status) => {
              const count = agents?.filter((a) => a.status === status).length ?? 0;
              if (count === 0) return null;
              return (
                <span key={status} className="inline-flex items-center gap-1.5">
                  <StatusBadge status={status} />
                  <span className="text-xs text-[var(--text-muted)]">{count}</span>
                </span>
              );
            })}
          </div>
        </div>
      </div>

      {/* Agent list */}
      <div className="neu-flat overflow-hidden">
        <div className="px-5 py-4">
          <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
            Agentes del Departamento
          </h2>
        </div>

        {agentsLoading ? (
          <div className="p-8">
            <LoadingSpinner />
          </div>
        ) : !agents || agents.length === 0 ? (
          <div className="px-5 pb-5">
            <EmptyState
              title="Sin agentes"
              description="Este departamento aun no tiene agentes asignados"
            />
          </div>
        ) : (
          <div className="px-3 pb-3 space-y-1">
            {agents.map((agent) => (
              <Link
                key={agent.id}
                to={`/agents/${agent.id}`}
                className="flex items-center justify-between px-4 py-3 rounded-xl hover:bg-white/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="neu-pressed w-10 h-10 rounded-xl flex items-center justify-center text-xs font-bold text-indigo-500">
                    {agent.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {agent.name}
                    </span>
                    <div className="flex items-center gap-2 mt-0.5">
                      {agent.role_name && (
                        <span className="text-xs text-[var(--text-muted)]">
                          {agent.role_name}
                        </span>
                      )}
                      <span
                        className={`text-xs font-medium ${
                          agent.origin === "internal"
                            ? "text-blue-400"
                            : "text-emerald-400"
                        }`}
                      >
                        {agent.origin}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {agent.capabilities && agent.capabilities.length > 0 && (
                    <div className="hidden md:flex gap-1">
                      {agent.capabilities.slice(0, 3).map((cap) => (
                        <span
                          key={cap}
                          className="neu-pressed-sm px-2 py-0.5 text-[11px] text-[var(--text-muted)]"
                        >
                          {cap}
                        </span>
                      ))}
                      {agent.capabilities.length > 3 && (
                        <span className="text-[11px] text-[var(--text-muted)]">
                          +{agent.capabilities.length - 3}
                        </span>
                      )}
                    </div>
                  )}
                  <StatusBadge status={agent.status} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
