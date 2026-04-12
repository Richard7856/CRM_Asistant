/**
 * Org Chart — visual hierarchy of agents grouped by department.
 *
 * Each department renders as a neumorphic card with:
 * - Department head (supervisor) as the anchor card
 * - Subordinates connected via CSS pseudo-element lines
 * - Status indicators and role badges
 * - Clickable agents that navigate to their detail page
 */

import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listAgents } from "@/api/agents";
import { listDepartments } from "@/api/departments";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import StatusBadge from "@/components/common/StatusBadge";
import { Network, Crown, Bot, Users, ChevronRight } from "lucide-react";

// Accent colors per department index — cycle for visual variety
const DEPT_ACCENTS = [
  { border: "border-indigo-400", bg: "bg-indigo-500/10", text: "text-indigo-500", dot: "bg-indigo-400" },
  { border: "border-emerald-400", bg: "bg-emerald-500/10", text: "text-emerald-500", dot: "bg-emerald-400" },
  { border: "border-amber-400", bg: "bg-amber-500/10", text: "text-amber-500", dot: "bg-amber-400" },
  { border: "border-rose-400", bg: "bg-rose-500/10", text: "text-rose-500", dot: "bg-rose-400" },
  { border: "border-cyan-400", bg: "bg-cyan-500/10", text: "text-cyan-500", dot: "bg-cyan-400" },
];

export default function OrgChartPage() {
  const navigate = useNavigate();

  const { data: agents, isLoading } = useQuery({
    queryKey: ["agents", { page: 1, size: 100 }],
    queryFn: () => listAgents({ page: 1, size: 100 }),
  });

  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => listDepartments({ page: 1, size: 50 }),
  });

  if (isLoading) return <LoadingSpinner />;

  const agentList = agents?.items ?? [];
  const deptList = departments?.items ?? [];

  // Group agents by department
  const agentsByDept = agentList.reduce(
    (acc, agent) => {
      const deptId = agent.department_id;
      if (!acc[deptId]) acc[deptId] = [];
      acc[deptId]!.push(agent);
      return acc;
    },
    {} as Record<string, typeof agentList>,
  );

  // Stats for the header
  const totalAgents = agentList.length;
  const onlineAgents = agentList.filter((a) => a.status === "active" || a.status === "idle").length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Network className="w-5 h-5 text-indigo-500" />
          <div>
            <h1 className="text-xl font-bold text-[var(--text-primary)]">Organigrama</h1>
            <p className="text-xs text-[var(--text-muted)]">
              Estructura jerárquica por departamento
            </p>
          </div>
        </div>
        {/* Summary pills */}
        <div className="flex items-center gap-3">
          <div className="neu-pressed-sm px-3 py-1.5 flex items-center gap-2">
            <Users className="w-3.5 h-3.5 text-[var(--text-muted)]" />
            <span className="text-xs font-medium text-[var(--text-primary)]">{totalAgents} agentes</span>
          </div>
          <div className="neu-pressed-sm px-3 py-1.5 flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400 dot-glow-green" />
            <span className="text-xs font-medium text-[var(--text-primary)]">{onlineAgents} online</span>
          </div>
        </div>
      </div>

      {/* Department cards */}
      <div className="space-y-6">
        {deptList.map((dept, deptIdx) => {
          const deptAgents = agentsByDept[dept.id] ?? [];
          const accent = DEPT_ACCENTS[deptIdx % DEPT_ACCENTS.length]!;

          // Separate supervisors (no supervisor_id or supervisor not in same dept) from subordinates
          const supervisors = deptAgents.filter(
            (a) => !a.supervisor_id || !deptAgents.find((d) => d.id === a.supervisor_id),
          );
          const getSubordinates = (supervisorId: string) =>
            deptAgents.filter((a) => a.supervisor_id === supervisorId);

          return (
            <div key={dept.id} className="neu-flat rounded-xl overflow-hidden">
              {/* Department header with accent top border */}
              <div className={`border-t-[3px] ${accent.border} px-6 py-4`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-xl ${accent.bg}`}>
                      <Users className={`w-4 h-4 ${accent.text}`} />
                    </div>
                    <div>
                      <h2 className="text-base font-semibold text-[var(--text-primary)]">
                        {dept.name}
                      </h2>
                      {dept.description && (
                        <p className="text-xs text-[var(--text-muted)] mt-0.5">{dept.description}</p>
                      )}
                    </div>
                  </div>
                  <span className="text-xs font-medium text-[var(--text-muted)] neu-pressed-sm px-2.5 py-1">
                    {deptAgents.length} {deptAgents.length === 1 ? "agente" : "agentes"}
                  </span>
                </div>
              </div>

              {/* Agent hierarchy */}
              <div className="px-6 pb-5">
                {deptAgents.length === 0 ? (
                  <p className="text-sm text-[var(--text-muted)] py-2">Sin agentes asignados</p>
                ) : (
                  <div className="space-y-3 mt-2">
                    {supervisors.map((sup) => {
                      const subs = getSubordinates(sup.id);
                      return (
                        <div key={sup.id}>
                          {/* Supervisor card — prominent with crown icon */}
                          <button
                            onClick={() => navigate(`/agents/${sup.id}`)}
                            className="w-full neu-sm rounded-xl p-3.5 flex items-center gap-3 hover:shadow-none transition-all duration-200 group text-left"
                          >
                            <div className={`neu-pressed w-10 h-10 rounded-xl flex items-center justify-center shrink-0`}>
                              <span className={`text-sm font-bold ${accent.text}`}>
                                {sup.name.slice(0, 2).toUpperCase()}
                              </span>
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="text-sm font-semibold text-[var(--text-primary)] truncate">
                                  {sup.name}
                                </p>
                                <Crown className={`w-3.5 h-3.5 ${accent.text} shrink-0`} />
                              </div>
                              <p className="text-[11px] text-[var(--text-muted)]">
                                {sup.role_name ?? "Supervisor"}
                              </p>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <StatusBadge status={sup.status} />
                              <ChevronRight className="w-3.5 h-3.5 text-[var(--text-muted)] opacity-0 group-hover:opacity-100 transition-opacity" />
                            </div>
                          </button>

                          {/* Subordinates — connected via left border line */}
                          {subs.length > 0 && (
                            <div className={`ml-5 mt-1 relative`}>
                              {/* Vertical connector line */}
                              <div
                                className={`absolute left-0 top-0 bottom-3 w-px ${accent.dot} opacity-30`}
                              />
                              <div className="space-y-0.5">
                                {subs.map((sub) => (
                                  <button
                                    key={sub.id}
                                    onClick={() => navigate(`/agents/${sub.id}`)}
                                    className="w-full flex items-center gap-3 pl-5 pr-3 py-2.5 rounded-lg hover:bg-[var(--neu-dark)]/10 transition-colors group text-left relative"
                                  >
                                    {/* Horizontal connector */}
                                    <div
                                      className={`absolute left-0 top-1/2 w-4 h-px ${accent.dot} opacity-30`}
                                    />
                                    {/* Dot at the junction */}
                                    <div className={`absolute left-[-2px] top-1/2 -translate-y-1/2 w-[5px] h-[5px] rounded-full ${accent.dot} opacity-50`} />

                                    <div className="neu-pressed-sm w-8 h-8 rounded-lg flex items-center justify-center shrink-0">
                                      <Bot className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                      <p className="text-sm text-[var(--text-primary)] truncate">
                                        {sub.name}
                                      </p>
                                      {sub.role_name && (
                                        <p className="text-[10px] text-[var(--text-muted)]">{sub.role_name}</p>
                                      )}
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0">
                                      <StatusBadge status={sub.status} />
                                      <ChevronRight className="w-3 h-3 text-[var(--text-muted)] opacity-0 group-hover:opacity-100 transition-opacity" />
                                    </div>
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
