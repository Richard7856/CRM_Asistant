import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listDepartments } from "@/api/departments";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import EmptyState from "@/components/common/EmptyState";

export default function DepartmentListPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["departments"],
    queryFn: () => listDepartments({ page: 1, size: 50 }),
  });

  if (isLoading) return <LoadingSpinner />;

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold text-[var(--text-primary)]">Departamentos</h1>

      {!data || data.items.length === 0 ? (
        <EmptyState title="No hay departamentos" description="Crea departamentos para organizar tus agentes" />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.items.map((dept) => (
            <Link
              key={dept.id}
              to={`/departments/${dept.id}`}
              className="neu-flat p-5 hover:shadow-none transition-shadow duration-200 cursor-pointer"
            >
              <h3 className="font-semibold text-[var(--text-primary)]">{dept.name}</h3>
              {dept.description && (
                <p className="text-sm text-[var(--text-secondary)] mt-1 line-clamp-2">{dept.description}</p>
              )}
              <p className="text-xs text-[var(--text-muted)] mt-3">{dept.agent_count ?? 0} agentes</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
