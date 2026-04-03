import { useState, KeyboardEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRoles, useAgents, useCreateInternalAgent } from "@/hooks/useAgents";
import { useDepartments } from "@/hooks/useDepartments";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import { ArrowLeft, ChevronDown, ChevronUp, X } from "lucide-react";

const schema = z.object({
  name: z.string().min(1, "El nombre es obligatorio"),
  description: z.string().optional(),
  department_id: z.string().min(1, "Selecciona un departamento"),
  role_id: z.string().min(1, "Selecciona un rol"),
  supervisor_id: z.string().optional(),
  avatar_url: z.string().url("URL invalida").optional().or(z.literal("")),
  system_prompt: z.string().optional(),
  model_provider: z.string().optional(),
  model_name: z.string().optional(),
  temperature: z.coerce.number().min(0).max(1).default(0.7),
  max_tokens: z.coerce.number().min(1).default(4096),
  tools_json: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

/* Neumorphic form input classes */
const INPUT = "w-full neu-pressed-sm px-4 py-2.5 text-sm text-[var(--text-primary)] bg-transparent outline-none placeholder:text-[var(--text-muted)]";
const SELECT = "w-full neu-pressed-sm px-4 py-2.5 text-sm text-[var(--text-secondary)] bg-transparent outline-none cursor-pointer";
const TEXTAREA = "w-full neu-pressed-sm px-4 py-2.5 text-sm text-[var(--text-primary)] bg-transparent outline-none placeholder:text-[var(--text-muted)] resize-none";

export default function CreateAgentPage() {
  const navigate = useNavigate();
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [capInput, setCapInput] = useState("");
  const [aiConfigOpen, setAiConfigOpen] = useState(true);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { data: departments, isLoading: depsLoading } = useDepartments();
  const { data: roles, isLoading: rolesLoading } = useRoles();
  const { data: agents } = useAgents({ size: 100 });
  const createMutation = useCreateInternalAgent();

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      temperature: 0.7,
      max_tokens: 4096,
      model_provider: "anthropic",
    },
  });

  const temperatureValue = watch("temperature");

  function handleCapKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      const val = capInput.trim();
      if (val && !capabilities.includes(val)) {
        setCapabilities((prev) => [...prev, val]);
      }
      setCapInput("");
    }
  }

  function removeCap(cap: string) {
    setCapabilities((prev) => prev.filter((c) => c !== cap));
  }

  async function onSubmit(values: FormValues) {
    setSubmitError(null);
    let tools: unknown[] | undefined;
    if (values.tools_json?.trim()) {
      try {
        tools = JSON.parse(values.tools_json);
      } catch {
        setSubmitError("El JSON de herramientas no es valido");
        return;
      }
    }

    try {
      const result = await createMutation.mutateAsync({
        name: values.name,
        description: values.description || undefined,
        department_id: values.department_id,
        role_id: values.role_id,
        supervisor_id: values.supervisor_id || undefined,
        capabilities: capabilities.length > 0 ? capabilities : undefined,
        avatar_url: values.avatar_url || undefined,
        system_prompt: values.system_prompt || undefined,
        model_provider: values.model_provider || undefined,
        model_name: values.model_name || undefined,
        temperature: values.temperature,
        max_tokens: values.max_tokens,
        tools,
      });
      navigate(`/agents/${result.id}`);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Error al crear el agente";
      setSubmitError(message);
    }
  }

  if (depsLoading || rolesLoading) return <LoadingSpinner />;

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <Link to="/agents" className="inline-flex items-center gap-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Agentes
      </Link>

      <h1 className="text-xl font-semibold text-[var(--text-primary)]">Crear Agente Interno</h1>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Basic Info */}
          <div className="neu-flat p-6 space-y-4">
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Informacion Basica
            </h2>

            <Field label="Nombre" error={errors.name?.message} required>
              <input {...register("name")} className={INPUT} placeholder="Nombre del agente" />
            </Field>

            <Field label="Descripcion">
              <textarea {...register("description")} rows={3} className={TEXTAREA} placeholder="Descripcion del agente..." />
            </Field>

            <Field label="Departamento" error={errors.department_id?.message} required>
              <select {...register("department_id")} className={SELECT}>
                <option value="">Seleccionar departamento</option>
                {departments?.items.map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </Field>

            <Field label="Rol" error={errors.role_id?.message} required>
              <select {...register("role_id")} className={SELECT}>
                <option value="">Seleccionar rol</option>
                {roles?.map((r) => (
                  <option key={r.id} value={r.id}>{r.name} ({r.level})</option>
                ))}
              </select>
            </Field>

            <Field label="Supervisor">
              <select {...register("supervisor_id")} className={SELECT}>
                <option value="">Sin supervisor</option>
                {agents?.items.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
            </Field>

            <Field label="Capacidades">
              <div className="flex flex-wrap gap-1.5 mb-2">
                {capabilities.map((cap) => (
                  <span key={cap} className="inline-flex items-center gap-1 px-2.5 py-1 neu-pressed-sm text-xs text-indigo-500 font-medium">
                    {cap}
                    <button type="button" onClick={() => removeCap(cap)} className="text-[var(--text-muted)] hover:text-red-400">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
              <input
                value={capInput}
                onChange={(e) => setCapInput(e.target.value)}
                onKeyDown={handleCapKeyDown}
                className={INPUT}
                placeholder="Escribe y presiona Enter"
              />
            </Field>

            <Field label="Avatar URL">
              <input {...register("avatar_url")} className={INPUT} placeholder="https://..." />
              {errors.avatar_url && <p className="text-xs text-red-400 mt-1">{errors.avatar_url.message}</p>}
            </Field>
          </div>

          {/* AI Configuration */}
          <div className="neu-flat overflow-hidden">
            <button
              type="button"
              onClick={() => setAiConfigOpen(!aiConfigOpen)}
              className="w-full flex items-center justify-between p-6 text-left"
            >
              <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                Configuracion IA
              </h2>
              {aiConfigOpen ? (
                <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" />
              ) : (
                <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />
              )}
            </button>

            {aiConfigOpen && (
              <div className="px-6 pb-6 space-y-4">
                <Field label="System Prompt" hint="El prompt que define el comportamiento del agente">
                  <textarea
                    {...register("system_prompt")}
                    rows={8}
                    className={`${TEXTAREA} font-mono`}
                    placeholder="Eres un agente de CRM especializado en..."
                  />
                </Field>

                <div className="grid grid-cols-2 gap-4">
                  <Field label="Proveedor">
                    <select {...register("model_provider")} className={SELECT}>
                      <option value="anthropic">Anthropic</option>
                      <option value="openai">OpenAI</option>
                      <option value="local">Local</option>
                    </select>
                  </Field>
                  <Field label="Modelo">
                    <input {...register("model_name")} className={INPUT} placeholder="claude-sonnet-4-20250514" />
                  </Field>
                </div>

                <Field label={`Temperatura: ${temperatureValue}`}>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    {...register("temperature")}
                    className="w-full accent-indigo-500"
                  />
                  <div className="flex justify-between text-[11px] text-[var(--text-muted)] mt-1">
                    <span>0 (Preciso)</span>
                    <span>1 (Creativo)</span>
                  </div>
                </Field>

                <Field label="Max Tokens">
                  <input type="number" {...register("max_tokens")} className={INPUT} />
                </Field>

                <Field label="Herramientas (JSON)" hint="Array JSON con definicion de herramientas">
                  <textarea
                    {...register("tools_json")}
                    rows={4}
                    className={`${TEXTAREA} font-mono`}
                    placeholder='[{"name": "search", "description": "..."}]'
                  />
                </Field>
              </div>
            )}
          </div>
        </div>

        {submitError && (
          <div className="neu-pressed p-4 text-red-400 text-sm">{submitError}</div>
        )}

        <div className="flex justify-end gap-3">
          <Link to="/agents" className="neu-sm px-5 py-2.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
            Cancelar
          </Link>
          <button
            type="submit"
            disabled={isSubmitting || createMutation.isPending}
            className="px-6 py-2.5 text-sm font-medium text-white bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-xl hover:from-indigo-600 hover:to-indigo-700 disabled:opacity-50 transition-all"
          >
            {createMutation.isPending ? "Creando..." : "Crear Agente"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  error,
  required,
  hint,
  children,
}: {
  label: string;
  error?: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
        {label}
        {required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      {hint && <p className="text-[11px] text-[var(--text-muted)] mb-1.5">{hint}</p>}
      {children}
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
    </div>
  );
}
