import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQuery } from "@tanstack/react-query";
import { listDepartments } from "@/api/departments";
import { listAgents } from "@/api/agents";
import { listTasks } from "@/api/tasks";
import { useCreateTask } from "@/hooks/useTasks";

const createTaskSchema = z.object({
  title: z.string().min(1, "El titulo es requerido"),
  description: z.string().optional(),
  priority: z.enum(["low", "medium", "high", "critical"]).default("medium"),
  department_id: z.string().optional(),
  assigned_to: z.string().optional(),
  due_at: z.string().optional(),
  parent_task_id: z.string().optional(),
});

type CreateTaskForm = z.infer<typeof createTaskSchema>;

export default function CreateTaskPage() {
  const navigate = useNavigate();
  const createTask = useCreateTask();

  const { data: departments } = useQuery({
    queryKey: ["departments", { page: 1, size: 50 }],
    queryFn: () => listDepartments({ page: 1, size: 50 }),
  });

  const { data: agents } = useQuery({
    queryKey: ["agents", { page: 1, size: 100 }],
    queryFn: () => listAgents({ page: 1, size: 100 }),
  });

  const { data: tasks } = useQuery({
    queryKey: ["tasks", { page: 1, size: 100 }],
    queryFn: () => listTasks({ page: 1, size: 100 }),
  });

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CreateTaskForm>({
    resolver: zodResolver(createTaskSchema),
    defaultValues: {
      priority: "medium",
    },
  });

  const onSubmit = async (data: CreateTaskForm) => {
    // Clean up empty strings to undefined
    const payload = {
      title: data.title,
      description: data.description || undefined,
      priority: data.priority,
      department_id: data.department_id || undefined,
      assigned_to: data.assigned_to || undefined,
      due_at: data.due_at ? new Date(data.due_at).toISOString() : undefined,
      parent_task_id: data.parent_task_id || undefined,
    };

    await createTask.mutateAsync(payload);
    navigate("/tasks");
  };

  const labelClass = "block text-sm font-medium text-gray-700 mb-1";
  const inputClass =
    "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none";
  const errorClass = "text-xs text-red-500 mt-1";

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Nueva Tarea</h1>
        <button
          onClick={() => navigate("/tasks")}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Cancelar
        </button>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="neu-flat rounded-xl p-6 space-y-5">
        {/* Title */}
        <div>
          <label className={labelClass}>
            Titulo <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            placeholder="Nombre de la tarea"
            className={inputClass}
            {...register("title")}
          />
          {errors.title && <p className={errorClass}>{errors.title.message}</p>}
        </div>

        {/* Description */}
        <div>
          <label className={labelClass}>Descripcion</label>
          <textarea
            rows={3}
            placeholder="Descripcion detallada de la tarea..."
            className={inputClass}
            {...register("description")}
          />
        </div>

        {/* Priority + Department row */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Prioridad</label>
            <select className={inputClass} {...register("priority")}>
              <option value="low">Baja</option>
              <option value="medium">Media</option>
              <option value="high">Alta</option>
              <option value="critical">Critica</option>
            </select>
          </div>
          <div>
            <label className={labelClass}>Departamento</label>
            <select className={inputClass} {...register("department_id")}>
              <option value="">Sin departamento</option>
              {(departments?.items ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Assigned To + Due Date row */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Asignar a</label>
            <select className={inputClass} {...register("assigned_to")}>
              <option value="">Sin asignar</option>
              {(agents?.items ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} — {a.department_name ?? "Sin depto"}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass}>Fecha limite</label>
            <input type="date" className={inputClass} {...register("due_at")} />
          </div>
        </div>

        {/* Parent Task */}
        <div>
          <label className={labelClass}>Tarea padre (opcional)</label>
          <select className={inputClass} {...register("parent_task_id")}>
            <option value="">Ninguna — es tarea principal</option>
            {(tasks?.items ?? []).map((t) => (
              <option key={t.id} value={t.id}>
                {t.title}
              </option>
            ))}
          </select>
        </div>

        {/* Error message */}
        {createTask.isError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
            <p className="text-sm text-red-600">
              Error al crear la tarea. Intente de nuevo.
            </p>
          </div>
        )}

        {/* Submit */}
        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={() => navigate("/tasks")}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={isSubmitting || createTask.isPending}
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {createTask.isPending ? "Creando..." : "Crear Tarea"}
          </button>
        </div>
      </form>
    </div>
  );
}
