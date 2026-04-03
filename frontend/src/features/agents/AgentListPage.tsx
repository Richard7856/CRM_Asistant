import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listAgents } from "@/api/agents";
import StatusBadge from "@/components/common/StatusBadge";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import EmptyState from "@/components/common/EmptyState";
import { formatRelative } from "@/lib/formatters";
import { Plus, ExternalLink } from "lucide-react";

export default function AgentListPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [originFilter, setOriginFilter] = useState<string>("");

  const { data, isLoading } = useQuery({
    queryKey: ["agents", { page, status: statusFilter, origin: originFilter }],
    queryFn: () =>
      listAgents({
        page,
        size: 20,
        status: statusFilter || undefined,
        origin: originFilter || undefined,
      }),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Agentes</h1>
        <div className="flex gap-3">
          <Link
            to="/agents/new"
            className="neu-sm flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-xl hover:from-indigo-600 hover:to-indigo-700 transition-all"
          >
            <Plus className="w-4 h-4" />
            Crear Agente
          </Link>
          <Link
            to="/agents/register"
            className="neu-sm flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            <ExternalLink className="w-4 h-4" />
            Registrar Externo
          </Link>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="neu-pressed-sm text-sm px-4 py-2 text-[var(--text-secondary)] bg-transparent outline-none cursor-pointer"
        >
          <option value="">Todos los estados</option>
          <option value="active">Activo</option>
          <option value="idle">Inactivo</option>
          <option value="busy">Ocupado</option>
          <option value="error">Error</option>
          <option value="offline">Offline</option>
        </select>
        <select
          value={originFilter}
          onChange={(e) => { setOriginFilter(e.target.value); setPage(1); }}
          className="neu-pressed-sm text-sm px-4 py-2 text-[var(--text-secondary)] bg-transparent outline-none cursor-pointer"
        >
          <option value="">Todos los origenes</option>
          <option value="internal">Interno</option>
          <option value="external">Externo</option>
        </select>
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="No hay agentes"
          description="Crea tu primer agente para comenzar"
        />
      ) : (
        <>
          <div className="neu-flat overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[var(--text-muted)]">
                  <th className="text-left px-5 py-4 text-xs font-medium uppercase tracking-wider">Nombre</th>
                  <th className="text-left px-5 py-4 text-xs font-medium uppercase tracking-wider">Departamento</th>
                  <th className="text-left px-5 py-4 text-xs font-medium uppercase tracking-wider">Rol</th>
                  <th className="text-left px-5 py-4 text-xs font-medium uppercase tracking-wider">Origen</th>
                  <th className="text-left px-5 py-4 text-xs font-medium uppercase tracking-wider">Estado</th>
                  <th className="text-left px-5 py-4 text-xs font-medium uppercase tracking-wider">Ultima actividad</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((agent) => (
                  <tr key={agent.id} className="hover:bg-white/30 transition-colors">
                    <td className="px-5 py-3.5">
                      <Link to={`/agents/${agent.id}`} className="font-medium text-indigo-500 hover:text-indigo-600 transition-colors">
                        {agent.name}
                      </Link>
                    </td>
                    <td className="px-5 py-3.5 text-[var(--text-secondary)]">{agent.department_name ?? "--"}</td>
                    <td className="px-5 py-3.5 text-[var(--text-secondary)] capitalize">{agent.role_name ?? "--"}</td>
                    <td className="px-5 py-3.5">
                      <span className={`text-xs font-medium px-2.5 py-1 rounded-lg ${
                        agent.origin === "internal"
                          ? "neu-pressed-sm text-blue-500"
                          : "neu-pressed-sm text-emerald-500"
                      }`}>
                        {agent.origin}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={agent.status} />
                    </td>
                    <td className="px-5 py-3.5 text-xs text-[var(--text-muted)]">
                      {agent.updated_at ? formatRelative(agent.updated_at) : "--"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.pages > 1 && (
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="neu-sm px-4 py-2 text-sm text-[var(--text-secondary)] disabled:opacity-40 transition-opacity"
              >
                Anterior
              </button>
              <span className="text-sm text-[var(--text-muted)]">
                {page} / {data.pages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                disabled={page === data.pages}
                className="neu-sm px-4 py-2 text-sm text-[var(--text-secondary)] disabled:opacity-40 transition-opacity"
              >
                Siguiente
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
