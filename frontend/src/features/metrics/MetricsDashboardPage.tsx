import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { getMetricOverview, getLeaderboard, getMetricsSummary } from "@/api/metrics";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import TrendLineChart, { CHART_COLORS } from "@/components/charts/TrendLineChart";
import AgentBarChart from "@/components/charts/AgentBarChart";
import StatusPieChart from "@/components/charts/StatusPieChart";
import { formatPercent, formatMs, formatCurrency, formatNumber } from "@/lib/formatters";

type RangeDays = 7 | 30 | 90;

export default function MetricsDashboardPage() {
  const [range, setRange] = useState<RangeDays>(30);

  const { data: overview, isLoading } = useQuery({
    queryKey: ["metrics", "overview"],
    queryFn: getMetricOverview,
  });

  const { data: leaderboard } = useQuery({
    queryKey: ["metrics", "leaderboard"],
    queryFn: () => getLeaderboard(10),
  });

  const { data: summary } = useQuery({
    queryKey: ["metrics", "summary"],
    queryFn: getMetricsSummary,
  });

  if (isLoading) return <LoadingSpinner />;

  // Prepare chart data from summary
  const dailyTasks = (summary?.daily_tasks ?? []).slice(-range);

  const successTrendData = dailyTasks.map((d) => {
    const total = d.completed + d.failed;
    return {
      date: d.date,
      tasa_exito: total > 0 ? d.completed / total : 0,
    };
  });

  const costTrendData = dailyTasks.map((d) => ({
    date: d.date,
    completadas: d.completed,
    fallidas: d.failed,
  }));

  const topAgentsData = (summary?.top_agents ?? []).slice(0, 10).map((a) => ({
    name: a.agent_name.length > 12 ? a.agent_name.slice(0, 12) + "..." : a.agent_name,
    value: a.tasks_completed,
  }));

  const taskStatusData = summary?.tasks_by_status
    ? Object.entries(summary.tasks_by_status).map(([status, count]) => ({
        name: statusLabel(status),
        value: count,
        color: statusColor(status),
      }))
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Metricas</h1>
        <select
          value={range}
          onChange={(e) => setRange(Number(e.target.value) as RangeDays)}
          className="text-sm border rounded-lg px-3 py-1.5 text-[var(--text-primary)] neu-pressed focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
        >
          <option value={7}>Ultimos 7 dias</option>
          <option value={30}>Ultimos 30 dias</option>
          <option value={90}>Ultimos 90 dias</option>
        </select>
      </div>

      {/* Overview KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <KpiCard
          title="Total Agentes"
          value={formatNumber(overview?.total_agents ?? 0)}
          accent="blue"
        />
        <KpiCard
          title="Agentes Activos"
          value={formatNumber(overview?.active_agents ?? 0)}
          accent="green"
        />
        <KpiCard
          title="Tareas Completadas Hoy"
          value={formatNumber(overview?.tasks_completed_today ?? 0)}
          accent="purple"
        />
        <KpiCard
          title="Tasa de Exito"
          value={overview?.overall_success_rate != null ? formatPercent(overview.overall_success_rate) : "--"}
          accent="green"
        />
        <KpiCard
          title="Latencia Promedio"
          value={overview?.avg_response_ms != null ? formatMs(overview.avg_response_ms) : "--"}
          accent="amber"
        />
        <KpiCard
          title="Costo Hoy"
          value={overview ? formatCurrency(overview.total_cost_today) : "--"}
          accent="red"
        />
      </div>

      {/* Charts Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Success Rate Trend */}
        <ChartCard title="Tendencia de Tasa de Exito">
          <TrendLineChart
            data={successTrendData}
            xKey="date"
            lines={[
              { dataKey: "tasa_exito", name: "Tasa de Exito", color: CHART_COLORS.green },
            ]}
            height={260}
            yDomain={[0, 1]}
            yTickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
            xTickFormatter={(v) => v.slice(5)}
          />
        </ChartCard>

        {/* Tasks per Agent */}
        <ChartCard title="Tareas Completadas por Agente (Top 10)">
          <AgentBarChart
            data={topAgentsData}
            height={260}
            color={CHART_COLORS.blue}
          />
        </ChartCard>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Task Completion Over Time (Area) */}
        <ChartCard title="Tareas Completadas y Fallidas por Dia">
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={costTrendData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 12, fill: "#9ca3af" }} tickFormatter={(v) => v.slice(5)} />
              <YAxis tick={{ fontSize: 12, fill: "#9ca3af" }} />
              <Tooltip
                contentStyle={{ backgroundColor: "#fff", border: "1px solid #e5e7eb", borderRadius: "8px", fontSize: "12px" }}
              />
              <Area
                type="monotone"
                dataKey="completadas"
                name="Completadas"
                stroke={CHART_COLORS.green}
                fill={CHART_COLORS.green}
                fillOpacity={0.2}
                stackId="1"
              />
              <Area
                type="monotone"
                dataKey="fallidas"
                name="Fallidas"
                stroke={CHART_COLORS.red}
                fill={CHART_COLORS.red}
                fillOpacity={0.2}
                stackId="1"
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Task Status Distribution */}
        <ChartCard title="Distribucion de Tareas por Estado">
          <StatusPieChart
            data={taskStatusData}
            height={260}
            innerRadius={50}
            outerRadius={90}
          />
        </ChartCard>
      </div>

      {/* Leaderboard */}
      <div className="neu-flat rounded-xl">
        <div className="p-4 border-b">
          <h2 className="text-sm font-semibold text-gray-700">Leaderboard - Top Agentes</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="neu-pressed-sm border-b border-[var(--neu-dark)]">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600 w-12">#</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Agente</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Tasa de Exito</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600 hidden sm:table-cell">Barra</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {(leaderboard ?? []).map((entry, i) => (
                <tr key={entry.agent_id} className="hover:bg-[var(--neu-dark)]/20 transition-colors">
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                      i === 0 ? "bg-yellow-100 text-yellow-700" :
                      i === 1 ? "bg-gray-100 text-gray-600" :
                      i === 2 ? "bg-orange-100 text-orange-700" :
                      "text-gray-400"
                    }`}>
                      {i + 1}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900">{entry.agent_name}</td>
                  <td className="px-4 py-3 text-right font-semibold">
                    <span className={entry.success_rate >= 0.8 ? "text-green-600" : entry.success_rate >= 0.5 ? "text-amber-600" : "text-red-600"}>
                      {formatPercent(entry.success_rate)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right hidden sm:table-cell">
                    <div className="w-full bg-gray-100 rounded-full h-2">
                      <div
                        className="h-2 rounded-full transition-all"
                        style={{
                          width: `${Math.min(entry.success_rate * 100, 100)}%`,
                          backgroundColor: entry.success_rate >= 0.8 ? CHART_COLORS.green : entry.success_rate >= 0.5 ? CHART_COLORS.amber : CHART_COLORS.red,
                        }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* ---- Helpers ---- */

const accentColors: Record<string, string> = {
  blue: "border-l-blue-500",
  green: "border-l-green-500",
  amber: "border-l-amber-500",
  red: "border-l-red-500",
  purple: "border-l-purple-500",
  cyan: "border-l-cyan-500",
};

function KpiCard({ title, value, accent = "blue" }: { title: string; value: string; accent?: string }) {
  return (
    <div className={`neu-flat rounded-xl border-l-4 ${accentColors[accent] ?? accentColors.blue} p-4 shadow-sm`}>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{title}</p>
      <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="neu-flat rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">{title}</h3>
      {children}
    </div>
  );
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "Pendiente",
    assigned: "Asignada",
    in_progress: "En progreso",
    review: "Revision",
    completed: "Completada",
    failed: "Fallida",
    cancelled: "Cancelada",
  };
  return labels[status] ?? status;
}

function statusColor(status: string): string {
  const colors: Record<string, string> = {
    pending: "#9ca3af",
    assigned: "#60a5fa",
    in_progress: "#3b82f6",
    review: "#8b5cf6",
    completed: "#10b981",
    failed: "#ef4444",
    cancelled: "#d1d5db",
  };
  return colors[status] ?? "#9ca3af";
}
