import { useQuery } from "@tanstack/react-query";
import { listImprovements } from "@/api/improvements";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import StatusBadge from "@/components/common/StatusBadge";
import { PRIORITY_COLORS } from "@/lib/constants";
import { formatRelative } from "@/lib/formatters";

const IMPROVEMENT_STATUS_COLORS: Record<string, string> = {
  identified: "bg-yellow-500",
  proposed: "bg-blue-400",
  approved: "bg-blue-600",
  in_progress: "bg-purple-500",
  implemented: "bg-green-500",
  dismissed: "bg-gray-400",
};

export default function ImprovementsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["improvements", { page: 1, size: 50 }],
    queryFn: () => listImprovements({ page: 1, size: 50 }),
  });

  if (isLoading) return <LoadingSpinner />;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Puntos de Mejora</h1>

      <div className="space-y-3">
        {(data?.items ?? []).map((item) => (
          <div key={item.id} className="neu-flat rounded-xl p-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-sm font-semibold">{item.title}</h3>
                <p className="text-xs text-gray-500 mt-1">{item.description}</p>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={item.priority} colorMap={PRIORITY_COLORS} />
                <StatusBadge status={item.status} colorMap={IMPROVEMENT_STATUS_COLORS} />
              </div>
            </div>
            <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
              <span>Agente: {item.agent_name ?? "--"}</span>
              <span>Categoria: {item.category}</span>
              <span>{formatRelative(item.created_at)}</span>
            </div>
            {item.resolution && (
              <p className="mt-2 text-xs text-green-700 bg-green-50 p-2 rounded">
                Resolucion: {item.resolution}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
