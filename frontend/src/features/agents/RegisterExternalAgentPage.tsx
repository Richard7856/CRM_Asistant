import { useState, KeyboardEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRoles, useAgents, useRegisterExternalAgent } from "@/hooks/useAgents";
import { useDepartments } from "@/hooks/useDepartments";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import { ArrowLeft, X, Copy, Check } from "lucide-react";

const schema = z.object({
  name: z.string().min(1, "El nombre es obligatorio"),
  description: z.string().optional(),
  department_id: z.string().min(1, "Selecciona un departamento"),
  role_id: z.string().min(1, "Selecciona un rol"),
  supervisor_id: z.string().optional(),
  platform: z.string().optional(),
  integration_type: z.string().min(1, "Selecciona un tipo de integracion"),
  endpoint_url: z.string().optional(),
  polling_interval_seconds: z.coerce.number().min(1).optional(),
  integration_config_json: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

const INPUT = "w-full neu-pressed-sm px-4 py-2.5 text-sm text-[var(--text-primary)] bg-transparent outline-none placeholder:text-[var(--text-muted)]";
const SELECT = "w-full neu-pressed-sm px-4 py-2.5 text-sm text-[var(--text-secondary)] bg-transparent outline-none cursor-pointer";
const TEXTAREA = "w-full neu-pressed-sm px-4 py-2.5 text-sm text-[var(--text-primary)] bg-transparent outline-none placeholder:text-[var(--text-muted)] resize-none";

export default function RegisterExternalAgentPage() {
  const navigate = useNavigate();
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [capInput, setCapInput] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [apiKeyModal, setApiKeyModal] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const { data: departments, isLoading: depsLoading } = useDepartments();
  const { data: roles, isLoading: rolesLoading } = useRoles();
  const { data: agents } = useAgents({ size: 100 });
  const registerMutation = useRegisterExternalAgent();

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      platform: "n8n",
      integration_type: "webhook",
    },
  });

  const integrationType = watch("integration_type");

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

  async function copyApiKey() {
    if (apiKeyModal) {
      await navigator.clipboard.writeText(apiKeyModal);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  async function onSubmit(values: FormValues) {
    setSubmitError(null);
    let integrationConfig: Record<string, unknown> | undefined;
    if (values.integration_config_json?.trim()) {
      try {
        integrationConfig = JSON.parse(values.integration_config_json);
      } catch {
        setSubmitError("El JSON de configuracion no es valido");
        return;
      }
    }

    try {
      const result = await registerMutation.mutateAsync({
        name: values.name,
        description: values.description || undefined,
        department_id: values.department_id,
        role_id: values.role_id,
        supervisor_id: values.supervisor_id || undefined,
        capabilities: capabilities.length > 0 ? capabilities : undefined,
        platform: values.platform || undefined,
        integration_type: values.integration_type,
        endpoint_url: values.endpoint_url || undefined,
        polling_interval_seconds: values.polling_interval_seconds,
        integration_config: integrationConfig,
      });
      setApiKeyModal(result.api_key);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Error al registrar el agente";
      setSubmitError(message);
    }
  }

  if (depsLoading || rolesLoading) return <LoadingSpinner />;

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* API Key Modal */}
      {apiKeyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm animate-fade-in">
          <div className="neu-flat p-6 max-w-lg w-full mx-4 space-y-4">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Agente Registrado</h2>
            <p className="text-sm text-[var(--text-secondary)]">
              Tu API key se muestra a continuacion. <strong>Guardala ahora</strong>, no se mostrara de nuevo.
            </p>
            <div className="neu-pressed p-3 flex items-center gap-2">
              <code className="flex-1 text-sm font-mono break-all text-[var(--text-primary)]">
                {apiKeyModal}
              </code>
              <button
                type="button"
                onClick={copyApiKey}
                className="shrink-0 p-2 neu-sm text-indigo-500 hover:text-indigo-600 transition-colors"
              >
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => navigate("/agents")}
                className="px-5 py-2.5 text-sm font-medium text-white bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-xl hover:from-indigo-600 hover:to-indigo-700 transition-all"
              >
                Ir a Agentes
              </button>
            </div>
          </div>
        </div>
      )}

      <Link to="/agents" className="inline-flex items-center gap-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Agentes
      </Link>

      <h1 className="text-xl font-semibold text-[var(--text-primary)]">Registrar Agente Externo</h1>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Basic Info */}
          <div className="neu-flat p-6 space-y-4">
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Informacion Basica
            </h2>

            <Field label="Nombre" error={errors.name?.message} required>
              <input {...register("name")} className={INPUT} placeholder="Nombre del agente externo" />
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
          </div>

          {/* Integration */}
          <div className="neu-flat p-6 space-y-4">
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Integracion
            </h2>

            <Field label="Plataforma">
              <select {...register("platform")} className={SELECT}>
                <option value="n8n">n8n</option>
                <option value="langchain">LangChain</option>
                <option value="crewai">CrewAI</option>
                <option value="custom">Custom</option>
              </select>
            </Field>

            <Field label="Tipo de Integracion" error={errors.integration_type?.message} required>
              <select {...register("integration_type")} className={SELECT}>
                <option value="webhook">Webhook</option>
                <option value="api_polling">API Polling</option>
                <option value="websocket">WebSocket</option>
                <option value="sdk">SDK</option>
              </select>
            </Field>

            <Field label="Endpoint URL">
              <input {...register("endpoint_url")} className={INPUT} placeholder="https://..." />
            </Field>

            {integrationType === "api_polling" && (
              <Field label="Intervalo de Polling (segundos)">
                <input type="number" {...register("polling_interval_seconds")} className={INPUT} placeholder="30" />
              </Field>
            )}

            <Field label="Config de Integracion (JSON)" hint="Configuracion adicional en formato JSON">
              <textarea
                {...register("integration_config_json")}
                rows={5}
                className={`${TEXTAREA} font-mono`}
                placeholder='{"auth_header": "X-API-Key", "retry_count": 3}'
              />
            </Field>
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
            disabled={isSubmitting || registerMutation.isPending}
            className="px-6 py-2.5 text-sm font-medium text-white bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-xl hover:from-indigo-600 hover:to-indigo-700 disabled:opacity-50 transition-all"
          >
            {registerMutation.isPending ? "Registrando..." : "Registrar Agente"}
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
