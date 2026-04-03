import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listAgents } from "@/api/agents";
import { listDepartments } from "@/api/departments";
import { listTasks } from "@/api/tasks";
import { listActivities } from "@/api/activities";
import { getMetricOverview } from "@/api/metrics";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import StatusBadge from "@/components/common/StatusBadge";
import StatusPieChart from "@/components/charts/StatusPieChart";
import AgentBarChart from "@/components/charts/AgentBarChart";
import { CHART_COLORS } from "@/components/charts/TrendLineChart";
import { TASK_STATUS_COLORS } from "@/lib/constants";
import { formatRelative, formatPercent } from "@/lib/formatters";
import type { Agent } from "@/types/agent";

const AGENT_STATUS_CHART_COLORS: Record<string, string> = {
  active: "#22c55e",
  idle: "#eab308",
  busy: "#3b82f6",
  error: "#ef4444",
  offline: "#9ca3af",
  maintenance: "#8b5cf6",
};

const AGENT_STATUS_LABELS: Record<string, string> = {
  active: "Activo",
  idle: "Inactivo",
  busy: "Ocupado",
  error: "Error",
  offline: "Desconectado",
  maintenance: "Mantenimiento",
};

export default function CeoDashboardPage() {
  const { data: agentsData, isLoading: loadingAgents } = useQuery({
    queryKey: ["agents", { page: 1, size: 100 }],
    queryFn: () => listAgents({ page: 1, size: 100 }),
  });

  const { data: departmentsData, isLoading: loadingDepts } = useQuery({
    queryKey: ["departments", { page: 1, size: 50 }],
    queryFn: () => listDepartments({ page: 1, size: 50 }),
  });

  const { data: tasksData, isLoading: loadingTasks } = useQuery({
    queryKey: ["tasks", { page: 1, size: 100 }],
    queryFn: () => listTasks({ page: 1, size: 100 }),
  });

  const { data: activities } = useQuery({
    queryKey: ["activities", { page: 1, size: 30 }],
    queryFn: () => listActivities({ page: 1, size: 30 }),
    refetchInterval: 10_000,
  });

  useQuery({
    queryKey: ["metrics", "overview"],
    queryFn: getMetricOverview,
  });

  if (loadingAgents || loadingDepts || loadingTasks) return <LoadingSpinner />;

  const agents = agentsData?.items ?? [];
  const departments = departmentsData?.items ?? [];
  const tasks = tasksData?.items ?? [];
  const activityItems = activities?.items ?? [];

  // --- Derived data ---
  const agentStatusCounts = agents.reduce(
    (acc, a) => {
      acc[a.status] = (acc[a.status] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  const taskStatusCounts = tasks.reduce(
    (acc, t) => {
      acc[t.status] = (acc[t.status] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  const completedTasks = taskStatusCounts["completed"] ?? 0;
  const failedTasks = taskStatusCounts["failed"] ?? 0;
  const totalFinished = completedTasks + failedTasks;
  const successRate = totalFinished > 0 ? completedTasks / totalFinished : 0;

  // Supervisors
  const supervisorIds = new Set(agents.map((a) => a.supervisor_id).filter(Boolean));
  const supervisors = agents.filter((a) => supervisorIds.has(a.id));

  // Alerts
  const errorAgents = agents.filter((a) => a.status === "error" || a.status === "offline");
  const staleAgents = agents.filter((a) => {
    if (!a.last_heartbeat_at) return false;
    const diff = Date.now() - new Date(a.last_heartbeat_at).getTime();
    return diff > 5 * 60 * 1000 && a.status !== "offline";
  });
  const failedTasksList = tasks.filter((t) => t.status === "failed");
  const alertCount = errorAgents.length + staleAgents.length + failedTasksList.length;

  // Agent task map
  const agentCurrentTask = new Map<string, string>();
  for (const t of tasks) {
    if (t.assigned_to && (t.status === "in_progress" || t.status === "assigned")) {
      agentCurrentTask.set(t.assigned_to, t.title);
    }
  }

  // Dept data
  const deptAgentCount = agents.reduce(
    (acc, a) => {
      acc[a.department_id] = (acc[a.department_id] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  const deptActiveTasks = tasks.reduce(
    (acc, t) => {
      if (t.department_id && t.status !== "completed" && t.status !== "failed" && t.status !== "cancelled") {
        acc[t.department_id] = (acc[t.department_id] ?? 0) + 1;
      }
      return acc;
    },
    {} as Record<string, number>,
  );

  // Donut chart data for agent status
  const agentDonutData = Object.entries(agentStatusCounts).map(([status, count]) => ({
    name: AGENT_STATUS_LABELS[status] ?? status,
    value: count,
    color: AGENT_STATUS_CHART_COLORS[status] ?? "#9ca3af",
  }));

  // Department performance bar chart
  const deptBarData = departments.map((dept) => {
    const count = deptAgentCount[dept.id] ?? 0;
    const activeTasks = deptActiveTasks[dept.id] ?? 0;
    return {
      name: dept.name.length > 15 ? dept.name.slice(0, 15) + "..." : dept.name,
      value: count + activeTasks,
      color: CHART_COLORS.blue,
    };
  }).sort((a, b) => b.value - a.value);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-[var(--text-primary)]">CEO / Orquestador</h1>

      {/* ===== TOP BAR - System Health ===== */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Agents Summary */}
        <div className="neu-flat rounded-xl p-4">
          <p className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wide">Agentes</p>
          <p className="text-2xl font-bold text-[var(--text-primary)] mt-1">{agents.length}</p>
          <div className="flex flex-wrap gap-3 mt-2">
            {Object.entries(agentStatusCounts).map(([status, count]) => (
              <div key={status} className="flex items-center gap-1.5">
                <StatusBadge status={status} />
                <span className="text-xs font-medium text-[var(--text-primary)]">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Tasks Summary */}
        <div className="neu-flat rounded-xl p-4">
          <p className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wide">Tareas</p>
          <p className="text-2xl font-bold text-[var(--text-primary)] mt-1">{tasks.length}</p>
          <div className="flex flex-wrap gap-3 mt-2">
            {Object.entries(taskStatusCounts).map(([status, count]) => (
              <div key={status} className="flex items-center gap-1.5">
                <StatusBadge status={status} colorMap={TASK_STATUS_COLORS} />
                <span className="text-xs font-medium text-[var(--text-primary)]">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Success Rate Gauge */}
        <div className="neu-flat rounded-xl p-4 flex flex-col items-center justify-center">
          <p className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wide">Tasa de Éxito</p>
          <div className="relative mt-2">
            <svg className="w-24 h-24" viewBox="0 0 100 100">
              {/* Track — use neu shadow color so it blends with theme */}
              <circle cx="50" cy="50" r="40" fill="none" stroke="var(--neu-dark)" strokeWidth="10" />
              <circle
                cx="50" cy="50" r="40" fill="none"
                stroke={successRate >= 0.8 ? "#22c55e" : successRate >= 0.5 ? "#f59e0b" : "#ef4444"}
                strokeWidth="10"
                strokeDasharray={`${successRate * 251.2} 251.2`}
                strokeLinecap="round"
                transform="rotate(-90 50 50)"
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-lg font-bold text-[var(--text-primary)]">{formatPercent(successRate)}</span>
            </div>
          </div>
          <p className="text-xs text-[var(--text-secondary)] mt-1">
            {completedTasks} completadas / {failedTasks} fallidas
          </p>
        </div>
      </div>

      {/* ===== Charts Row: Donut + Dept Performance ===== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="neu-flat rounded-xl p-4">
          <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-1">Distribución de Estado de Agentes</h2>
          <StatusPieChart
            data={agentDonutData}
            height={260}
            innerRadius={55}
            outerRadius={90}
          />
        </div>

        <div className="neu-flat rounded-xl p-4">
          <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-1">Rendimiento por Departamento</h2>
          <p className="text-xs text-[var(--text-secondary)] mb-2">Agentes + tareas activas</p>
          <AgentBarChart
            data={deptBarData}
            height={240}
            layout="vertical"
            color={CHART_COLORS.blue}
          />
        </div>
      </div>

      {/* ===== SECTION 1 - Department Overview ===== */}
      <div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-3">Departamentos</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {departments.map((dept) => {
            const agentCount = deptAgentCount[dept.id] ?? 0;
            const activeTasks = deptActiveTasks[dept.id] ?? 0;
            const headAgent = dept.head_agent_id
              ? agents.find((a) => a.id === dept.head_agent_id)
              : null;
            const hasErrors = agents.some(
              (a) => a.department_id === dept.id && (a.status === "error" || a.status === "offline"),
            );
            // Border color signals department health at a glance
            const borderColor = hasErrors
              ? "border-red-400"
              : agentCount === 0
                ? "border-[var(--neu-dark)]"
                : "border-green-400";

            return (
              <div
                key={dept.id}
                className={`neu-flat rounded-xl border-2 ${borderColor} p-4 transition-shadow`}
              >
                <p className="text-sm font-semibold text-[var(--text-primary)]">{dept.name}</p>
                <div className="mt-2 space-y-1 text-xs text-[var(--text-secondary)]">
                  <p>Agentes: <span className="font-medium text-[var(--text-primary)]">{agentCount}</span></p>
                  <p>Tareas activas: <span className="font-medium text-[var(--text-primary)]">{activeTasks}</span></p>
                  <p>
                    Jefe:{" "}
                    <span className="font-medium text-[var(--text-primary)]">
                      {headAgent?.name ?? "Sin asignar"}
                    </span>
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ===== SECTION 2 - Agent Matrix ===== */}
      <AgentMatrixTable agents={agents} agentCurrentTask={agentCurrentTask} />

      {/* ===== SECTION 3 - Supervisor Tree ===== */}
      <SupervisorTree agents={agents} supervisors={supervisors} />

      {/* ===== SECTION 4 - Recent Activity + Alerts ===== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Activity Feed */}
        <div className="neu-flat rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--neu-dark)]">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Actividad Reciente</h2>
          </div>
          <div className="divide-y divide-[var(--neu-dark)] max-h-96 overflow-y-auto">
            {activityItems.length === 0 ? (
              <p className="p-4 text-sm text-[var(--text-secondary)]">Sin actividad reciente.</p>
            ) : (
              activityItems.map((log) => (
                <div key={log.id} className="px-4 py-3 hover:neu-pressed transition-all">
                  <p className="text-sm">
                    <span className="font-medium text-[var(--text-primary)]">{log.agent_name ?? "Agente"}</span>{" "}
                    <span className="text-[var(--text-secondary)]">{log.action}</span>
                  </p>
                  {log.summary && (
                    <p className="text-xs text-[var(--text-secondary)] mt-0.5">{log.summary}</p>
                  )}
                  <p className="text-xs text-[var(--text-secondary)] mt-1 opacity-60">{formatRelative(log.occurred_at)}</p>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Alerts */}
        <div className={`neu-flat rounded-xl overflow-hidden ${alertCount > 0 ? "ring-2 ring-red-400/50" : ""}`}>
          <div className={`px-4 py-3 border-b border-[var(--neu-dark)] flex items-center justify-between ${alertCount > 0 ? "bg-red-500/10" : ""}`}>
            <h2 className="text-sm font-semibold text-[var(--text-primary)] flex items-center gap-2">
              Alertas
              {alertCount > 0 && (
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold">
                  {alertCount}
                </span>
              )}
            </h2>
          </div>
          <div className="divide-y divide-[var(--neu-dark)] max-h-96 overflow-y-auto">
            {alertCount === 0 ? (
              <div className="p-4 flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
                <p className="text-sm text-green-600 font-medium">Sin alertas. Todo en orden.</p>
              </div>
            ) : (
              <>
                {errorAgents.map((a) => (
                  <div key={a.id} className="px-4 py-3 flex items-center gap-3 bg-red-500/10">
                    <span className="w-2.5 h-2.5 rounded-full bg-red-500 flex-shrink-0 animate-pulse" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-red-600">
                        {a.name} — {a.status === "error" ? "Error" : "Desconectado"}
                      </p>
                      <p className="text-xs text-[var(--text-secondary)]">{a.department_name ?? "Sin depto"}</p>
                    </div>
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-red-600 bg-red-500/20 px-2 py-0.5 rounded-full">
                      Crítico
                    </span>
                  </div>
                ))}
                {staleAgents.map((a) => (
                  <div key={`stale-${a.id}`} className="px-4 py-3 flex items-center gap-3 bg-yellow-500/10">
                    <span className="w-2.5 h-2.5 rounded-full bg-yellow-500 flex-shrink-0" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-yellow-600">
                        {a.name} — heartbeat inactivo
                      </p>
                      <p className="text-xs text-[var(--text-secondary)]">
                        Último: {a.last_heartbeat_at ? formatRelative(a.last_heartbeat_at) : "nunca"}
                      </p>
                    </div>
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-yellow-600 bg-yellow-500/20 px-2 py-0.5 rounded-full">
                      Advertencia
                    </span>
                  </div>
                ))}
                {failedTasksList.slice(0, 10).map((t) => (
                  <div key={t.id} className="px-4 py-3 flex items-center gap-3">
                    <span className="w-2.5 h-2.5 rounded-full bg-red-400 flex-shrink-0" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-red-500">
                        Tarea fallida: {t.title}
                      </p>
                      <p className="text-xs text-[var(--text-secondary)]">
                        {t.assignee_name ?? "Sin asignar"} &middot; {formatRelative(t.updated_at)}
                      </p>
                    </div>
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-red-500 bg-red-500/10 px-2 py-0.5 rounded-full">
                      Fallida
                    </span>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ================= Sub-components ================= */

function AgentMatrixTable({
  agents,
  agentCurrentTask,
}: {
  agents: Agent[];
  agentCurrentTask: Map<string, string>;
}) {
  const [sortKey, setSortKey] = useState<keyof Agent>("name");
  const [sortAsc, setSortAsc] = useState(true);

  const handleSort = (key: keyof Agent) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const sorted = [...agents].sort((a, b) => {
    const aVal = (a[sortKey] ?? "") as string;
    const bVal = (b[sortKey] ?? "") as string;
    const cmp = String(aVal).localeCompare(String(bVal));
    return sortAsc ? cmp : -cmp;
  });

  // Row tints are semitransparent so they work over the neumorphic background
  const statusRowColor: Record<string, string> = {
    active: "",
    idle: "bg-yellow-400/10",
    busy: "bg-blue-400/10",
    error: "bg-red-400/10",
    offline: "bg-gray-400/10",
    maintenance: "bg-purple-400/10",
  };

  const sortArrow = (key: keyof Agent) =>
    sortKey === key ? (sortAsc ? " ↑" : " ↓") : "";

  const th = "text-left px-4 py-3 font-medium text-[var(--text-secondary)] cursor-pointer hover:text-[var(--text-primary)] select-none";

  return (
    <div>
      <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-3">Matriz de Agentes</h2>
      <div className="neu-flat rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          {/* Header pressed in so it reads as a distinct section */}
          <thead className="neu-pressed-sm border-b border-[var(--neu-dark)]">
            <tr>
              <th className={th} onClick={() => handleSort("name")}>Nombre{sortArrow("name")}</th>
              <th className={th} onClick={() => handleSort("department_name" as keyof Agent)}>Departamento{sortArrow("department_name" as keyof Agent)}</th>
              <th className={th} onClick={() => handleSort("role_name" as keyof Agent)}>Rol{sortArrow("role_name" as keyof Agent)}</th>
              <th className={th} onClick={() => handleSort("status")}>Estado{sortArrow("status")}</th>
              <th className={th} onClick={() => handleSort("supervisor_name" as keyof Agent)}>Supervisor{sortArrow("supervisor_name" as keyof Agent)}</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">Tarea Actual</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">Capacidades</th>
              <th className={th} onClick={() => handleSort("last_heartbeat_at" as keyof Agent)}>Heartbeat{sortArrow("last_heartbeat_at" as keyof Agent)}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--neu-dark)]">
            {sorted.map((agent) => (
              <tr key={agent.id} className={`${statusRowColor[agent.status] ?? ""} hover:bg-[var(--neu-dark)]/20 transition-colors`}>
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">{agent.name}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{agent.department_name ?? "--"}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{agent.role_name ?? "--"}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={agent.status} />
                </td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{agent.supervisor_name ?? "--"}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)] max-w-[200px] truncate">
                  {agentCurrentTask.get(agent.id) ?? "--"}
                </td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{agent.capabilities.length}</td>
                <td className="px-4 py-3 text-xs text-[var(--text-secondary)] opacity-70">
                  {agent.last_heartbeat_at ? formatRelative(agent.last_heartbeat_at) : "Sin datos"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SupervisorTree({
  agents,
  supervisors,
}: {
  agents: Agent[];
  supervisors: Agent[];
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div>
      <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-3">Árbol de Supervisores</h2>
      <div className="neu-flat rounded-xl divide-y divide-[var(--neu-dark)] overflow-hidden">
        {supervisors.length === 0 ? (
          <p className="p-4 text-sm text-[var(--text-secondary)]">No hay supervisores registrados.</p>
        ) : (
          supervisors.map((sup) => {
            const subordinates = agents.filter((a) => a.supervisor_id === sup.id);
            const isExpanded = expanded.has(sup.id);

            return (
              <div key={sup.id}>
                <button
                  onClick={() => toggle(sup.id)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-[var(--neu-dark)]/20 text-left transition-colors"
                >
                  <div className="flex items-center gap-3">
                    {/* Avatar uses indigo tint — same as the app's accent */}
                    <div className="w-8 h-8 rounded-full bg-indigo-500/20 flex items-center justify-center text-xs font-bold text-indigo-500">
                      {sup.name.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-[var(--text-primary)]">{sup.name}</p>
                      <p className="text-xs text-[var(--text-secondary)]">
                        {sup.department_name ?? "Sin depto"} &middot; {sup.role_name ?? ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={sup.status} />
                    <span className="text-xs text-[var(--text-secondary)]">
                      {subordinates.length} subordinado{subordinates.length !== 1 ? "s" : ""}
                    </span>
                    <span className="text-[var(--text-secondary)] text-xs">{isExpanded ? "▲" : "▼"}</span>
                  </div>
                </button>

                {isExpanded && subordinates.length > 0 && (
                  // Pressed inset for subordinate rows — visually "inside" the supervisor row
                  <div className="neu-pressed-sm border-t border-[var(--neu-dark)] divide-y divide-[var(--neu-dark)]">
                    {subordinates.map((sub) => (
                      <div key={sub.id} className="flex items-center justify-between px-8 py-2.5">
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-full bg-[var(--neu-dark)]/40 flex items-center justify-center text-[10px] font-bold text-[var(--text-secondary)]">
                            {sub.name.slice(0, 2).toUpperCase()}
                          </div>
                          <span className="text-sm text-[var(--text-primary)]">{sub.name}</span>
                        </div>
                        <StatusBadge status={sub.status} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
