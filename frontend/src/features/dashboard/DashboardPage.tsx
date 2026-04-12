import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, ResponsiveContainer, XAxis, Tooltip } from "recharts";
import { listAgents } from "@/api/agents";
import { listActivities } from "@/api/activities";
import { getMetricOverview, getMetricsSummary } from "@/api/metrics";
import { listDepartments } from "@/api/departments";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import StatusBadge from "@/components/common/StatusBadge";
import Sparkline from "@/components/charts/Sparkline";
import { CHART_COLORS } from "@/components/charts/TrendLineChart";
import { formatRelative, formatPercent, formatCurrency, formatNumber } from "@/lib/formatters";
import { useNavigate } from "react-router-dom";
import { Users, CheckCircle, TrendingUp, DollarSign, Zap } from "lucide-react";

export default function DashboardPage() {
  const navigate = useNavigate();
  const { data: agents, isLoading: loadingAgents } = useQuery({
    queryKey: ["agents", { page: 1, size: 50 }],
    queryFn: () => listAgents({ page: 1, size: 50 }),
  });

  const { data: activities, isLoading: loadingActivities } = useQuery({
    queryKey: ["activities", { page: 1, size: 20 }],
    queryFn: () => listActivities({ page: 1, size: 20 }),
    refetchInterval: 10_000,
  });

  const { data: overview } = useQuery({
    queryKey: ["metrics", "overview"],
    queryFn: getMetricOverview,
  });

  const { data: summary } = useQuery({
    queryKey: ["metrics", "summary"],
    queryFn: getMetricsSummary,
  });

  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => listDepartments({ page: 1, size: 20 }),
  });

  if (loadingAgents) return <LoadingSpinner />;

  const statusCounts = (agents?.items ?? []).reduce(
    (acc, a) => {
      acc[a.status] = (acc[a.status] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  const dailyTasks = summary?.daily_tasks ?? [];
  const last7 = dailyTasks.slice(-7);
  const successSparkline = last7.map((d) => {
    const total = d.completed + d.failed;
    return { value: total > 0 ? d.completed / total : 0 };
  });

  // Top agents by cost — used for the cost breakdown widget
  const topAgentsByCost = [...(summary?.top_agents ?? [])]
    .sort((a, b) => b.cost_usd - a.cost_usd)
    .slice(0, 5);
  const maxAgentCost = topAgentsByCost.length > 0 ? topAgentsByCost[0]!.cost_usd : 1;

  const dailyBarData = last7.map((d) => ({
    date: d.date.slice(5),
    completadas: d.completed,
    fallidas: d.failed,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-[var(--text-primary)]">Dashboard</h1>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        <KpiCard
          title="Agentes Activos"
          value={`${overview?.active_agents ?? statusCounts["active"] ?? 0} / ${agents?.total ?? 0}`}
          Icon={Users}
          iconColor="text-indigo-500"
          sparkline={null}
        />
        <KpiCard
          title="Tareas Hoy"
          value={`${formatNumber(overview?.tasks_completed_today ?? 0)}`}
          Icon={CheckCircle}
          iconColor="text-emerald-500"
          sparkline={null}
        />
        <KpiCard
          title="Tasa de Exito"
          value={overview ? formatPercent(overview.overall_success_rate) : "--"}
          Icon={TrendingUp}
          iconColor="text-blue-500"
          sparkline={
            successSparkline.length >= 2 ? (
              <Sparkline data={successSparkline} color={CHART_COLORS.green} height={28} width={72} />
            ) : null
          }
        />
        <KpiCard
          title="Costo Hoy"
          value={overview ? formatCurrency(overview.total_cost_today) : "--"}
          Icon={DollarSign}
          iconColor="text-amber-500"
          sparkline={null}
        />
      </div>

      {/* Daily task chart */}
      {dailyBarData.length > 0 && (
        <div className="neu-flat p-5">
          <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
            Tareas Diarias — Ultimos 7 dias
          </h2>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={dailyBarData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--neu-bg)",
                  border: "none",
                  borderRadius: "12px",
                  boxShadow: "4px 4px 8px 0 var(--neu-dark), -4px -4px 8px 0 var(--neu-light)",
                  fontSize: "12px",
                }}
              />
              <Bar dataKey="completadas" name="Completadas" fill="#34d399" radius={[6, 6, 0, 0]} stackId="a" />
              <Bar dataKey="fallidas" name="Fallidas" fill="#f87171" radius={[6, 6, 0, 0]} stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Status summary */}
      <div className="neu-flat p-5">
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-3">
          Estado de Agentes
        </h2>
        <div className="flex flex-wrap gap-3">
          {Object.entries(statusCounts).map(([status, count]) => (
            <div key={status} className="flex items-center gap-2">
              <StatusBadge status={status} />
              <span className="text-sm font-bold text-[var(--text-primary)]">{count}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Agent List */}
        <div className="lg:col-span-2 neu-flat overflow-hidden">
          <div className="px-5 py-4">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Agentes</h2>
          </div>
          <div className="max-h-96 overflow-y-auto px-3 pb-3 space-y-2">
            {(agents?.items ?? []).map((agent) => (
              <div
                key={agent.id}
                className="flex items-center justify-between px-4 py-3 rounded-xl hover:bg-[var(--neu-bg)] transition-colors neu-sm"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-indigo-500/10 flex items-center justify-center text-xs font-bold text-indigo-500">
                    {agent.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">{agent.name}</p>
                    <p className="text-xs text-[var(--text-muted)]">
                      {agent.department_name ?? "Sin departamento"} · {agent.origin}
                    </p>
                  </div>
                </div>
                <StatusBadge status={agent.status} />
              </div>
            ))}
          </div>
        </div>

        {/* Activity Feed */}
        <div className="neu-flat overflow-hidden">
          <div className="px-5 py-4">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Actividad Reciente</h2>
          </div>
          <div className="max-h-96 overflow-y-auto px-4 pb-4 space-y-3">
            {loadingActivities ? (
              <LoadingSpinner />
            ) : (
              (activities?.items ?? []).map((log) => (
                <div key={log.id} className="py-2.5">
                  <p className="text-sm">
                    <span className="font-medium text-[var(--text-primary)]">
                      {log.agent_name ?? "Agente"}
                    </span>{" "}
                    <span className="text-[var(--text-secondary)]">{log.action}</span>
                  </p>
                  {log.summary && (
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">{log.summary}</p>
                  )}
                  <p className="text-[11px] text-[var(--text-muted)] mt-1">
                    {formatRelative(log.occurred_at)}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Department overview */}
        {departments && departments.items.length > 0 && (
          <div className="neu-flat p-5">
            <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-4">Departamentos</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {departments.items.map((dept) => (
                <div
                  key={dept.id}
                  onClick={() => navigate(`/departments/${dept.id}`)}
                  className="neu-sm p-4 hover:shadow-none transition-shadow duration-200 cursor-pointer"
                >
                  <p className="text-sm font-medium text-[var(--text-primary)]">{dept.name}</p>
                  <p className="text-xs text-[var(--text-muted)] mt-1">
                    {dept.agent_count ?? 0} agentes
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Cost Breakdown — shows which agents consume the most tokens/cost */}
        {topAgentsByCost.length > 0 && (
          <div className="neu-flat p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-amber-500" />
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                  Costo por Agente
                </h2>
              </div>
              <span className="text-xs text-[var(--text-muted)]">
                Total: {formatCurrency(summary?.total_cost_usd ?? 0)}
              </span>
            </div>
            <div className="space-y-3">
              {topAgentsByCost.map((agent) => {
                const pct = maxAgentCost > 0 ? (agent.cost_usd / maxAgentCost) * 100 : 0;
                return (
                  <div key={agent.agent_id} className="group">
                    <div className="flex items-center justify-between mb-1">
                      <button
                        onClick={() => navigate(`/agents/${agent.agent_id}`)}
                        className="text-sm font-medium text-[var(--text-primary)] hover:text-indigo-500 transition-colors truncate max-w-[60%] text-left"
                      >
                        {agent.agent_name}
                      </button>
                      <div className="flex items-center gap-3 text-xs">
                        <span className="text-[var(--text-muted)]">
                          {agent.tasks_completed} tareas
                        </span>
                        <span className="font-semibold text-[var(--text-primary)]">
                          {formatCurrency(agent.cost_usd)}
                        </span>
                      </div>
                    </div>
                    {/* Cost bar — visual proportion relative to top spender */}
                    <div className="h-2 rounded-full neu-pressed-sm overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-amber-400 to-amber-500 transition-all duration-500"
                        style={{ width: `${Math.max(pct, 3)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            {/* Token usage summary */}
            {summary && (
              <div className="mt-4 pt-3 border-t border-[var(--neu-dark)]/10 flex items-center justify-between text-xs text-[var(--text-muted)]">
                <span>{formatNumber(summary.total_token_usage)} tokens totales</span>
                <span>{summary.agents_measured} agentes medidos</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function KpiCard({
  title,
  value,
  Icon,
  iconColor,
  sparkline,
}: {
  title: string;
  value: string;
  Icon: React.ElementType;
  iconColor: string;
  sparkline?: React.ReactNode;
}) {
  return (
    <div className="neu-flat p-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="neu-pressed-sm p-2">
              <Icon className={`w-4 h-4 ${iconColor}`} />
            </div>
          </div>
          <p className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
            {title}
          </p>
          <p className="text-2xl font-bold text-[var(--text-primary)] mt-1">{value}</p>
        </div>
        {sparkline && <div className="mt-6">{sparkline}</div>}
      </div>
    </div>
  );
}
