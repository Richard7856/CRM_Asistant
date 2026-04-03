import { useQuery } from "@tanstack/react-query";
import { listAgents } from "@/api/agents";
import { listDepartments } from "@/api/departments";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import StatusBadge from "@/components/common/StatusBadge";

export default function OrgChartPage() {
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
    {} as Record<string, typeof agentList>
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Organigrama</h1>
      <p className="text-sm text-gray-500">
        Estructura jerarquica de agentes organizados por departamento
      </p>

      <div className="space-y-8">
        {deptList.map((dept) => {
          const deptAgents = agentsByDept[dept.id] ?? [];
          // Separate supervisors and regular agents
          const supervisors = deptAgents.filter((a) => !a.supervisor_id || !deptAgents.find((d) => d.id === a.supervisor_id));
          const getSubordinates = (supervisorId: string) =>
            deptAgents.filter((a) => a.supervisor_id === supervisorId);

          return (
            <div key={dept.id} className="neu-flat rounded-xl p-6">
              <h2 className="text-lg font-semibold mb-4">{dept.name}</h2>
              {dept.description && (
                <p className="text-sm text-gray-500 mb-4">{dept.description}</p>
              )}

              {deptAgents.length === 0 ? (
                <p className="text-sm text-gray-400">Sin agentes asignados</p>
              ) : (
                <div className="space-y-4">
                  {supervisors.map((sup) => (
                    <div key={sup.id}>
                      <div className="flex items-center gap-3 p-3 bg-indigo-50 rounded-lg">
                        <div className="w-8 h-8 rounded-full bg-indigo-200 flex items-center justify-center text-xs font-bold text-indigo-800">
                          {sup.name.slice(0, 2).toUpperCase()}
                        </div>
                        <div className="flex-1">
                          <p className="text-sm font-semibold">{sup.name}</p>
                          <p className="text-xs text-gray-500">{sup.role_name ?? sup.origin}</p>
                        </div>
                        <StatusBadge status={sup.status} />
                      </div>

                      {/* Subordinates */}
                      {getSubordinates(sup.id).length > 0 && (
                        <div className="ml-8 mt-2 space-y-1 border-l-2 border-indigo-200 pl-4">
                          {getSubordinates(sup.id).map((sub) => (
                            <div key={sub.id} className="flex items-center gap-3 p-2 rounded hover:bg-[var(--neu-dark)]/20">
                              <div className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center text-xs font-bold text-gray-600">
                                {sub.name.slice(0, 2).toUpperCase()}
                              </div>
                              <div className="flex-1">
                                <p className="text-sm">{sub.name}</p>
                              </div>
                              <StatusBadge status={sub.status} />
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
