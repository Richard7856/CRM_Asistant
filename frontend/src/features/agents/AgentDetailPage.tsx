import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getAgent, getSubordinates, updateAgent } from "@/api/agents";
import { listActivities } from "@/api/activities";
import { listTasks } from "@/api/tasks";
import StatusBadge from "@/components/common/StatusBadge";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import { formatDateTime, formatDate, formatRelative } from "@/lib/formatters";
import { LOG_LEVEL_COLORS, TASK_STATUS_COLORS, PRIORITY_COLORS } from "@/lib/constants";
import { useAgentCredentials } from "@/hooks/useCredentials";
import { ArrowLeft, Copy, Check, Power, Wrench, Key, Shield, ShieldOff, Server } from "lucide-react";

type Tab = "overview" | "activity" | "tasks" | "tools" | "subordinates";

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [copiedPrompt, setCopiedPrompt] = useState(false);

  const { data: agent, isLoading } = useQuery({
    queryKey: ["agent", id],
    queryFn: () => getAgent(id!),
    enabled: !!id,
  });

  const { data: subordinates } = useQuery({
    queryKey: ["agent", id, "subordinates"],
    queryFn: () => getSubordinates(id!),
    enabled: !!id,
  });

  const { data: activities, isLoading: activitiesLoading } = useQuery({
    queryKey: ["activities", { agent_id: id, page: 1, size: 20 }],
    queryFn: () => listActivities({ agent_id: id, page: 1, size: 20 }),
    enabled: !!id && activeTab === "activity",
  });

  const { data: tasks, isLoading: tasksLoading } = useQuery({
    queryKey: ["tasks", { assigned_to: id, page: 1, size: 20 }],
    queryFn: () => listTasks({ assigned_to: id, page: 1, size: 20 }),
    enabled: !!id && activeTab === "tasks",
  });

  const { data: agentCredentials } = useAgentCredentials(
    activeTab === "tools" ? id : undefined
  );

  if (isLoading || !agent) return <LoadingSpinner />;

  const hasSubordinates = (subordinates?.length ?? 0) > 0;

  const tools = agent.definition?.tools ?? [];
  const credCount = agentCredentials?.length ?? 0;
  const hasTools = tools.length > 0 || credCount > 0 || agent.origin === "internal";

  const tabs: { key: Tab; label: string; hidden?: boolean }[] = [
    { key: "overview", label: "Overview" },
    { key: "activity", label: "Actividad" },
    { key: "tasks", label: "Tareas" },
    { key: "tools", label: "Herramientas", hidden: !hasTools },
    { key: "subordinates", label: "Subordinados", hidden: !hasSubordinates },
  ];

  const handleCopyPrompt = () => {
    if (agent.definition?.system_prompt) {
      navigator.clipboard.writeText(agent.definition.system_prompt);
      setCopiedPrompt(true);
      setTimeout(() => setCopiedPrompt(false), 2000);
    }
  };

  const handleDeactivate = async () => {
    if (!confirm("Estas seguro que deseas desactivar este agente?")) return;
    await updateAgent(id!, { status: "offline" });
  };

  return (
    <div className="space-y-6">
      <Link to="/agents" className="inline-flex items-center gap-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Agentes
      </Link>

      {/* ───── Header ───── */}
      <div className="neu-flat p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="neu-pressed w-14 h-14 rounded-2xl flex items-center justify-center text-lg font-bold text-indigo-500">
              {agent.name.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <h1 className="text-xl font-semibold text-[var(--text-primary)]">{agent.name}</h1>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {agent.department_name && (
                  <span className="neu-pressed-sm px-2.5 py-1 text-xs font-medium text-blue-500">
                    {agent.department_name}
                  </span>
                )}
                {agent.role_name && (
                  <span className="neu-pressed-sm px-2.5 py-1 text-xs font-medium text-violet-500">
                    {agent.role_name}
                  </span>
                )}
                <span className={`neu-pressed-sm px-2.5 py-1 text-xs font-medium ${
                  agent.origin === "internal" ? "text-blue-500" : "text-emerald-500"
                }`}>
                  {agent.origin}
                </span>
                <StatusBadge status={agent.status} />
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate(`/agents/${id}/edit`)}
              className="neu-sm px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Editar
            </button>
            <button
              onClick={handleDeactivate}
              className="neu-sm p-2.5 text-red-400 hover:text-red-500 transition-colors"
              title="Desactivar"
            >
              <Power className="w-4 h-4" />
            </button>
          </div>
        </div>

        {agent.description && (
          <p className="mt-4 text-sm text-[var(--text-secondary)]">{agent.description}</p>
        )}
      </div>

      {/* ───── Tab Navigation ───── */}
      <div className="neu-pressed-sm flex gap-1 p-1 w-fit">
        {tabs
          .filter((t) => !t.hidden)
          .map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                activeTab === tab.key
                  ? "neu-sm text-indigo-500"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              {tab.label}
              {tab.key === "subordinates" && hasSubordinates && (
                <span className="ml-1.5 text-[11px] text-[var(--text-muted)]">
                  {subordinates!.length}
                </span>
              )}
            </button>
          ))}
      </div>

      {/* ───── Tab Content ───── */}

      {/* OVERVIEW */}
      {activeTab === "overview" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="neu-flat p-5 space-y-4">
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Informacion Basica
            </h2>
            <div className="space-y-3">
              <InfoRow label="Departamento" value={agent.department_name ?? "--"} />
              <InfoRow label="Rol" value={agent.role_name ?? "--"} />
              <div className="flex justify-between text-sm">
                <span className="text-[var(--text-muted)]">Supervisor</span>
                {agent.supervisor_id ? (
                  <Link
                    to={`/agents/${agent.supervisor_id}`}
                    className="font-medium text-indigo-500 hover:text-indigo-600 transition-colors"
                  >
                    {agent.supervisor_name ?? "Ver"}
                  </Link>
                ) : (
                  <span className="text-[var(--text-muted)]">Ninguno</span>
                )}
              </div>
              <div className="flex justify-between text-sm items-start">
                <span className="text-[var(--text-muted)]">Capacidades</span>
                <div className="flex flex-wrap justify-end gap-1.5 max-w-[60%]">
                  {(agent.capabilities as string[]).length > 0 ? (
                    (agent.capabilities as string[]).map((cap) => (
                      <span key={cap} className="neu-pressed-sm px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                        {cap}
                      </span>
                    ))
                  ) : (
                    <span className="text-[var(--text-muted)]">--</span>
                  )}
                </div>
              </div>
              <InfoRow label="Creado" value={formatDateTime(agent.created_at)} />
              <InfoRow
                label="Ultimo Heartbeat"
                value={agent.last_heartbeat_at ? formatRelative(agent.last_heartbeat_at) : "N/A"}
              />
            </div>
          </div>

          <div className="space-y-6">
            {/* Internal agent details */}
            {agent.origin === "internal" && (
              <>
                {agent.definition?.system_prompt && (
                  <div className="neu-flat overflow-hidden">
                    <div className="flex items-center justify-between px-5 py-4">
                      <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                        System Prompt
                      </h2>
                      <button
                        onClick={handleCopyPrompt}
                        className="neu-sm p-2 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                      >
                        {copiedPrompt ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                    <div className="neu-pressed mx-4 mb-4 p-4 rounded-xl">
                      <pre className="text-sm font-mono whitespace-pre-wrap overflow-auto max-h-72 leading-relaxed text-[var(--text-secondary)]">
                        {agent.definition.system_prompt}
                      </pre>
                    </div>
                  </div>
                )}

                {agent.definition && (
                  <div className="neu-flat p-5 space-y-4">
                    <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                      Configuracion del Modelo
                    </h2>
                    <div className="space-y-3">
                      <InfoRow label="Proveedor" value={agent.definition.model_provider ?? "--"} />
                      <InfoRow label="Modelo" value={agent.definition.model_name ?? "--"} />
                      <div className="flex justify-between text-sm items-center">
                        <span className="text-[var(--text-muted)]">Temperatura</span>
                        <div className="flex items-center gap-2">
                          <div className="w-24 h-2 rounded-full overflow-hidden neu-pressed-sm">
                            <div
                              className="h-full bg-gradient-to-r from-blue-400 to-orange-400 rounded-full transition-all"
                              style={{ width: `${(agent.definition.temperature / 1) * 100}%` }}
                            />
                          </div>
                          <span className="font-medium text-xs text-[var(--text-secondary)]">
                            {agent.definition.temperature.toFixed(2)}
                          </span>
                        </div>
                      </div>
                      <InfoRow label="Max Tokens" value={String(agent.definition.max_tokens)} />
                      <InfoRow label="Version" value={`v${agent.definition.version}`} />
                    </div>
                  </div>
                )}

                {agent.definition?.tools && agent.definition.tools.length > 0 && (
                  <div className="neu-flat p-5 space-y-3">
                    <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                      Herramientas
                    </h2>
                    <div className="flex flex-wrap gap-2">
                      {agent.definition.tools.map((tool, idx) => (
                        <span key={idx} className="neu-pressed-sm px-3 py-1.5 text-xs font-medium text-indigo-500">
                          {typeof tool === "string"
                            ? tool
                            : (tool as Record<string, unknown>).name
                              ? String((tool as Record<string, unknown>).name)
                              : `Tool ${idx + 1}`}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* External agent details */}
            {agent.origin === "external" && agent.integration && (
              <>
                <div className="neu-flat p-5 space-y-4">
                  <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                    Integracion
                  </h2>
                  <div className="space-y-3">
                    <InfoRow label="Plataforma" value={agent.integration.platform ?? "Custom"} />
                    <InfoRow label="Tipo" value={agent.integration.integration_type} />
                    {agent.integration.endpoint_url && (
                      <div className="flex justify-between text-sm items-start">
                        <span className="text-[var(--text-muted)]">Endpoint</span>
                        <span className="font-mono text-xs neu-pressed-sm px-2 py-1 max-w-[60%] truncate text-[var(--text-secondary)]">
                          {agent.integration.endpoint_url}
                        </span>
                      </div>
                    )}
                    <div className="flex justify-between text-sm">
                      <span className="text-[var(--text-muted)]">Activo</span>
                      <span className={`font-medium ${agent.integration.is_active ? "text-emerald-500" : "text-red-400"}`}>
                        {agent.integration.is_active ? "Si" : "No"}
                      </span>
                    </div>
                    <InfoRow label="Ultimo Sync" value={agent.integration.last_sync_at ? formatRelative(agent.integration.last_sync_at) : "Nunca"} />
                    <InfoRow label="Intervalo Polling" value={`${agent.integration.polling_interval_seconds}s`} />
                  </div>
                </div>

                {agent.integration.config &&
                  Array.isArray((agent.integration.config as Record<string, unknown>).api_keys) && (
                    <div className="neu-flat p-5 space-y-3">
                      <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                        API Keys
                      </h2>
                      <div className="space-y-2">
                        {((agent.integration.config as Record<string, unknown>).api_keys as Array<{
                          prefix?: string;
                          key?: string;
                          scopes?: string[];
                        }>).map((keyEntry, idx) => (
                          <div key={idx} className="flex items-center justify-between neu-pressed-sm px-3 py-2">
                            <span className="text-sm font-mono text-[var(--text-secondary)]">
                              {keyEntry.prefix ?? keyEntry.key?.slice(0, 8) ?? "key"}********
                            </span>
                            {keyEntry.scopes && (
                              <div className="flex gap-1">
                                {keyEntry.scopes.map((scope) => (
                                  <span key={scope} className="px-2 py-0.5 text-[11px] text-[var(--text-muted)]">
                                    {scope}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
              </>
            )}
          </div>
        </div>
      )}

      {/* ACTIVITY TAB */}
      {activeTab === "activity" && (
        <div className="neu-flat overflow-hidden">
          <div className="px-5 py-4">
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Actividad Reciente
            </h2>
          </div>
          {activitiesLoading ? (
            <div className="p-8"><LoadingSpinner /></div>
          ) : (activities?.items ?? []).length === 0 ? (
            <p className="px-5 pb-5 text-sm text-[var(--text-muted)] text-center">
              Sin actividad registrada.
            </p>
          ) : (
            <div className="px-3 pb-3 space-y-2">
              {(activities?.items ?? []).map((log) => (
                <div key={log.id} className="flex items-start gap-4 px-4 py-3 rounded-xl hover:bg-white/30 transition-colors">
                  <div className="mt-1.5 flex-shrink-0">
                    <div className={`w-2.5 h-2.5 rounded-full ${
                      log.level === "error" || log.level === "critical"
                        ? "bg-red-400 dot-glow-red"
                        : log.level === "warning"
                          ? "bg-amber-400 dot-glow-yellow"
                          : log.level === "info"
                            ? "bg-blue-400 dot-glow-blue"
                            : "bg-[var(--text-muted)] dot-glow-gray"
                    }`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[var(--text-primary)]">{log.action}</span>
                        <span className={`text-xs font-medium capitalize ${LOG_LEVEL_COLORS[log.level] ?? "text-[var(--text-muted)]"}`}>
                          {log.level}
                        </span>
                      </div>
                      <span className="text-[11px] text-[var(--text-muted)] flex-shrink-0">
                        {formatDateTime(log.occurred_at)}
                      </span>
                    </div>
                    {log.summary && (
                      <p className="text-sm text-[var(--text-secondary)] mt-0.5">{log.summary}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TASKS TAB */}
      {activeTab === "tasks" && (
        <div className="neu-flat overflow-hidden">
          <div className="px-5 py-4">
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Tareas Asignadas
            </h2>
          </div>
          {tasksLoading ? (
            <div className="p-8"><LoadingSpinner /></div>
          ) : (tasks?.items ?? []).length === 0 ? (
            <p className="px-5 pb-5 text-sm text-[var(--text-muted)] text-center">
              Sin tareas asignadas.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[var(--text-muted)]">
                  <th className="text-left px-5 py-3 text-xs font-medium uppercase tracking-wider">Titulo</th>
                  <th className="text-left px-5 py-3 text-xs font-medium uppercase tracking-wider">Estado</th>
                  <th className="text-left px-5 py-3 text-xs font-medium uppercase tracking-wider">Prioridad</th>
                  <th className="text-left px-5 py-3 text-xs font-medium uppercase tracking-wider">Limite</th>
                  <th className="text-left px-5 py-3 text-xs font-medium uppercase tracking-wider">Creada</th>
                </tr>
              </thead>
              <tbody>
                {(tasks?.items ?? []).map((task) => (
                  <tr key={task.id} className="hover:bg-white/30 cursor-pointer transition-colors" onClick={() => navigate(`/tasks/${task.id}`)}>
                    <td className="px-5 py-3 font-medium text-[var(--text-primary)] max-w-xs truncate">{task.title}</td>
                    <td className="px-5 py-3"><StatusBadge status={task.status} colorMap={TASK_STATUS_COLORS} /></td>
                    <td className="px-5 py-3"><StatusBadge status={task.priority} colorMap={PRIORITY_COLORS} /></td>
                    <td className="px-5 py-3 text-[var(--text-muted)]">{task.due_at ? formatDate(task.due_at) : "--"}</td>
                    <td className="px-5 py-3 text-[var(--text-muted)]">{formatDate(task.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* TOOLS TAB — agent tools + credentials */}
      {activeTab === "tools" && (
        <div className="space-y-5">
          {/* Tools from definition */}
          {tools.length > 0 && (
            <div className="neu-flat p-5 rounded-xl">
              <div className="flex items-center gap-2 mb-4">
                <Wrench className="w-4 h-4 text-indigo-400" />
                <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                  Herramientas Configuradas
                </h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {tools.map((tool, idx) => {
                  const toolName = typeof tool === "string"
                    ? tool
                    : (tool as Record<string, unknown>).name
                      ? String((tool as Record<string, unknown>).name)
                      : `Tool ${idx + 1}`;
                  const toolDesc = typeof tool !== "string" && (tool as Record<string, unknown>).description
                    ? String((tool as Record<string, unknown>).description)
                    : null;
                  return (
                    <div key={idx} className="neu-pressed rounded-lg p-3">
                      <p className="text-sm font-medium text-indigo-500">{toolName}</p>
                      {toolDesc && (
                        <p className="text-xs text-[var(--text-muted)] mt-1 line-clamp-2">{toolDesc}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {tools.length === 0 && (
            <div className="neu-flat p-5 rounded-xl">
              <div className="flex items-center gap-2 mb-2">
                <Wrench className="w-4 h-4 text-[var(--text-muted)]" />
                <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                  Herramientas
                </h2>
              </div>
              <p className="text-sm text-[var(--text-muted)]">
                Este agente no tiene herramientas configuradas aún. Las herramientas MCP se pueden asignar desde Integraciones.
              </p>
            </div>
          )}

          {/* Credentials available to this agent */}
          <div className="neu-flat p-5 rounded-xl">
            <div className="flex items-center gap-2 mb-4">
              <Key className="w-4 h-4 text-amber-500" />
              <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                Credenciales Disponibles
              </h2>
              <span className="ml-auto text-[11px] text-[var(--text-muted)]">
                {credCount} {credCount === 1 ? "credencial" : "credenciales"}
              </span>
            </div>
            {credCount === 0 ? (
              <p className="text-sm text-[var(--text-muted)]">
                Sin credenciales asignadas. Puedes crear credenciales desde la sección{" "}
                <Link to="/credentials" className="text-indigo-500 hover:text-indigo-600 font-medium">
                  Credenciales
                </Link>
                .
              </p>
            ) : (
              <div className="space-y-2">
                {agentCredentials!.map((cred) => (
                  <div key={cred.id} className="neu-pressed rounded-lg p-3 flex items-center justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={`p-1.5 rounded-lg ${cred.is_active ? "bg-emerald-50" : "bg-[var(--neu-dark)]/10"}`}>
                        {cred.is_active ? (
                          <Shield className="w-3.5 h-3.5 text-emerald-500" />
                        ) : (
                          <ShieldOff className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                        )}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-[var(--text-primary)] truncate">{cred.name}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <Server className="w-3 h-3 text-[var(--text-muted)]" />
                          <span className="text-[11px] text-[var(--text-muted)]">{cred.service_name}</span>
                          <code className="text-[11px] font-mono text-[var(--text-muted)]">{cred.secret_preview}</code>
                        </div>
                      </div>
                    </div>
                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                      cred.agent_id ? "bg-indigo-50 text-indigo-600" : "bg-[var(--neu-dark)]/10 text-[var(--text-muted)]"
                    }`}>
                      {cred.agent_id ? "Asignada" : "Compartida"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* SUBORDINATES TAB */}
      {activeTab === "subordinates" && hasSubordinates && (
        <div className="neu-flat overflow-hidden">
          <div className="px-5 py-4">
            <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Agentes Subordinados ({subordinates!.length})
            </h2>
          </div>
          <div className="px-3 pb-3 space-y-2">
            {subordinates!.map((sub) => (
              <Link
                key={sub.id}
                to={`/agents/${sub.id}`}
                className="flex items-center justify-between px-4 py-3 rounded-xl hover:bg-white/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="neu-pressed w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold text-indigo-500">
                    {sub.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <span className="text-sm font-medium text-[var(--text-primary)]">{sub.name}</span>
                    {sub.department_name && (
                      <p className="text-xs text-[var(--text-muted)]">
                        {sub.department_name}{sub.role_name ? ` - ${sub.role_name}` : ""}
                      </p>
                    )}
                  </div>
                </div>
                <StatusBadge status={sub.status} />
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-[var(--text-muted)]">{label}</span>
      <span className="font-medium text-[var(--text-primary)]">{value}</span>
    </div>
  );
}
