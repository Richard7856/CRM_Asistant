import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listActivities } from "@/api/activities";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import { LOG_LEVEL_COLORS } from "@/lib/constants";
import { formatDateTime } from "@/lib/formatters";

export default function ActivityLogPage() {
  const [page, setPage] = useState(1);
  const [levelFilter, setLevelFilter] = useState<string>("");

  const { data, isLoading } = useQuery({
    queryKey: ["activities", { page, level: levelFilter }],
    queryFn: () => listActivities({ page, size: 30, level: levelFilter || undefined }),
    refetchInterval: 10_000,
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Actividad</h1>
        <select
          value={levelFilter}
          onChange={(e) => { setLevelFilter(e.target.value); setPage(1); }}
          className="neu-pressed-sm text-sm px-4 py-2 text-[var(--text-secondary)] bg-transparent outline-none cursor-pointer"
        >
          <option value="">Todos los niveles</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="error">Error</option>
          <option value="critical">Critical</option>
        </select>
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : (
        <div className="neu-flat overflow-hidden">
          <div className="space-y-1 p-3">
            {(data?.items ?? []).map((log) => (
              <div key={log.id} className="flex items-start gap-4 px-4 py-3 rounded-xl hover:bg-white/30 transition-colors">
                <span className={`text-xs font-mono mt-0.5 ${LOG_LEVEL_COLORS[log.level] ?? ""}`}>
                  {log.level.toUpperCase().padEnd(8)}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-[var(--text-primary)]">{log.agent_name ?? "Agente"}</span>
                    <span className="text-sm text-[var(--text-secondary)]">{log.action}</span>
                  </div>
                  {log.summary && <p className="text-xs text-[var(--text-muted)] mt-0.5">{log.summary}</p>}
                </div>
                <span className="text-[11px] text-[var(--text-muted)] whitespace-nowrap">
                  {formatDateTime(log.occurred_at)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {data && data.pages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="neu-sm px-4 py-2 text-sm text-[var(--text-secondary)] disabled:opacity-40"
          >
            Anterior
          </button>
          <span className="text-sm text-[var(--text-muted)]">
            {page} / {data.pages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
            disabled={page === data.pages}
            className="neu-sm px-4 py-2 text-sm text-[var(--text-secondary)] disabled:opacity-40"
          >
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
}
