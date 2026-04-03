import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listAgents, getAgent, sendHeartbeat } from "@/api/agents";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import type { Agent, AgentDetail } from "@/types/agent";

const PLATFORM_BADGES: Record<string, { label: string; bg: string; text: string }> = {
  n8n: { label: "n8n", bg: "bg-orange-100", text: "text-orange-700" },
  langchain: { label: "LangChain", bg: "bg-green-100", text: "text-green-700" },
  crewai: { label: "CrewAI", bg: "bg-blue-100", text: "text-blue-700" },
  openai: { label: "OpenAI", bg: "bg-gray-100", text: "text-gray-700" },
  autogen: { label: "AutoGen", bg: "bg-purple-100", text: "text-purple-700" },
  custom: { label: "Custom", bg: "bg-gray-100", text: "text-gray-600" },
};

function getPlatformBadge(platform: string | null | undefined): { label: string; bg: string; text: string } {
  const fallback = { label: "Custom", bg: "bg-gray-100", text: "text-gray-600" };
  if (!platform) return fallback;
  const key = platform.toLowerCase();
  for (const [k, v] of Object.entries(PLATFORM_BADGES)) {
    if (key.includes(k)) return v;
  }
  return { label: platform, bg: "bg-gray-100", text: "text-gray-600" };
}

export default function IntegrationsPage() {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  const { data: agentsData, isLoading } = useQuery({
    queryKey: ["agents", { page: 1, size: 100, origin: "external" }],
    queryFn: () => listAgents({ page: 1, size: 100, origin: "external" }),
  });

  const { data: allAgents } = useQuery({
    queryKey: ["agents", { page: 1, size: 100 }],
    queryFn: () => listAgents({ page: 1, size: 100 }),
  });

  const { data: agentDetail, isLoading: loadingDetail } = useQuery({
    queryKey: ["agent", selectedAgentId],
    queryFn: () => getAgent(selectedAgentId!),
    enabled: !!selectedAgentId,
  });

  const queryClient = useQueryClient();
  const heartbeatMutation = useMutation({
    mutationFn: (agentId: string) => sendHeartbeat(agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  if (isLoading) return <LoadingSpinner />;

  const externalAgents = agentsData?.items ?? [];
  // Also show internal agents with integrations
  const internalAgents = (allAgents?.items ?? []).filter((a) => a.origin === "internal");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Integraciones</h1>
        <p className="text-sm text-gray-500 mt-1">
          Gestiona conexiones con agentes externos y plataformas de IA.
        </p>
      </div>

      {/* External Agents */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">
          Agentes Externos ({externalAgents.length})
        </h2>
        {externalAgents.length === 0 ? (
          <div className="neu-flat rounded-xl p-8 text-center">
            <p className="text-gray-400 text-sm">No hay agentes externos registrados.</p>
            <p className="text-xs text-gray-400 mt-2">
              Registra agentes externos desde la seccion de Agentes para verlos aqui.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {externalAgents.map((agent) => (
              <AgentIntegrationCard
                key={agent.id}
                agent={agent}
                isSelected={selectedAgentId === agent.id}
                onSelect={() => setSelectedAgentId(selectedAgentId === agent.id ? null : agent.id)}
                onHealthCheck={() => heartbeatMutation.mutate(agent.id)}
                isCheckingHealth={heartbeatMutation.isPending && heartbeatMutation.variables === agent.id}
              />
            ))}
          </div>
        )}
      </div>

      {/* Detail Panel */}
      {selectedAgentId && (
        <DetailPanel detail={agentDetail} loading={loadingDetail} />
      )}

      {/* Internal Agents Summary */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">
          Agentes Internos ({internalAgents.length})
        </h2>
        <div className="neu-flat rounded-xl">
          <div className="divide-y max-h-64 overflow-y-auto">
            {internalAgents.length === 0 ? (
              <p className="p-4 text-sm text-gray-400">No hay agentes internos.</p>
            ) : (
              internalAgents.map((agent) => (
                <div key={agent.id} className="flex items-center justify-between px-4 py-3 hover:bg-[var(--neu-dark)]/20 transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-xs font-bold text-indigo-700">
                      {agent.name.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">{agent.name}</p>
                      <p className="text-xs text-gray-500">{agent.department_name ?? "Sin departamento"}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <HealthDot status={agent.status} />
                    <span className="text-xs text-gray-500 capitalize">{agent.status}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Supported Platforms */}
      <div className="neu-flat rounded-xl p-4">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Plataformas Soportadas</h2>
        <div className="flex flex-wrap gap-3">
          {Object.entries(PLATFORM_BADGES).map(([key, badge]) => (
            <div
              key={key}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg ${badge.bg} ${badge.text} text-sm font-medium`}
            >
              <span className="w-2 h-2 rounded-full bg-current opacity-60" />
              {badge.label}
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-3">
          Conecta agentes de cualquier plataforma via API REST, webhooks o message queue.
        </p>
      </div>
    </div>
  );
}

/* ---- Sub-components ---- */

function HealthDot({ status }: { status: string }) {
  const color =
    status === "active" || status === "idle" || status === "busy"
      ? "bg-green-500"
      : status === "error"
        ? "bg-red-500"
        : status === "offline"
          ? "bg-gray-400"
          : "bg-yellow-500";

  return <span className={`w-2.5 h-2.5 rounded-full ${color}`} />;
}

function AgentIntegrationCard({
  agent,
  isSelected,
  onSelect,
  onHealthCheck,
  isCheckingHealth,
}: {
  agent: Agent;
  isSelected: boolean;
  onSelect: () => void;
  onHealthCheck: () => void;
  isCheckingHealth: boolean;
}) {
  const healthColor =
    agent.status === "active" || agent.status === "idle" || agent.status === "busy"
      ? "green"
      : agent.status === "error"
        ? "red"
        : "gray";

  const platformStr = (agent.metadata?.platform as string | undefined) ?? null;
  const badge = getPlatformBadge(platformStr);

  return (
    <div
      className={`neu-flat rounded-xl p-4 cursor-pointer transition-all hover:shadow-md ${
        isSelected ? "ring-2 ring-indigo-400 border-indigo-300" : ""
      }`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-sm font-bold text-indigo-700">
            {agent.name.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900">{agent.name}</p>
            <p className="text-xs text-gray-500">{agent.department_name ?? "Sin departamento"}</p>
          </div>
        </div>
        <HealthDot status={agent.status} />
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${badge.bg} ${badge.text}`}>
          {badge.label}
        </span>
        <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
          {agent.origin}
        </span>
        {agent.capabilities.slice(0, 3).map((cap) => (
          <span key={cap} className="text-[10px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">
            {cap}
          </span>
        ))}
        {agent.capabilities.length > 3 && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-50 text-gray-500">
            +{agent.capabilities.length - 3}
          </span>
        )}
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onHealthCheck();
          }}
          disabled={isCheckingHealth}
          className={`text-xs font-medium px-3 py-1.5 rounded-lg transition-colors ${
            healthColor === "green"
              ? "bg-green-50 text-green-700 hover:bg-green-100"
              : healthColor === "red"
                ? "bg-red-50 text-red-700 hover:bg-red-100"
                : "bg-gray-50 text-gray-600 hover:bg-gray-100"
          } disabled:opacity-50`}
        >
          {isCheckingHealth ? "Verificando..." : "Verificar Salud"}
        </button>
        <span className={`text-[10px] font-medium ${
          healthColor === "green" ? "text-green-600" :
          healthColor === "red" ? "text-red-600" :
          "text-gray-400"
        }`}>
          {healthColor === "green" ? "Saludable" : healthColor === "red" ? "No saludable" : "Desconocido"}
        </span>
      </div>
    </div>
  );
}

function DetailPanel({ detail, loading }: { detail?: AgentDetail; loading: boolean }) {
  if (loading) {
    return (
      <div className="neu-flat rounded-xl p-6">
        <LoadingSpinner />
      </div>
    );
  }

  if (!detail) return null;

  const integration = detail.integration;
  const definition = detail.definition;

  return (
    <div className="neu-flat rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        Detalles de Integracion: {detail.name}
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Integration Info */}
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide">Integracion</h4>
          {integration ? (
            <div className="space-y-2 text-sm">
              <InfoRow label="Tipo" value={integration.integration_type} />
              <InfoRow label="Plataforma" value={integration.platform ?? "--"} />
              <InfoRow label="Endpoint" value={integration.endpoint_url ?? "--"} mono />
              <InfoRow label="Intervalo de polling" value={`${integration.polling_interval_seconds}s`} />
              <InfoRow label="Activa" value={integration.is_active ? "Si" : "No"} />
              <InfoRow label="Ultima sincronizacion" value={integration.last_sync_at ?? "Nunca"} />
            </div>
          ) : (
            <p className="text-xs text-gray-400">Sin datos de integracion.</p>
          )}
        </div>

        {/* Definition Info */}
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide">Definicion</h4>
          {definition ? (
            <div className="space-y-2 text-sm">
              <InfoRow label="Proveedor" value={definition.model_provider ?? "--"} />
              <InfoRow label="Modelo" value={definition.model_name ?? "--"} />
              <InfoRow label="Temperatura" value={String(definition.temperature)} />
              <InfoRow label="Max Tokens" value={String(definition.max_tokens)} />
              <InfoRow label="Herramientas" value={`${definition.tools.length} configuradas`} />
              <InfoRow label="Version" value={`v${definition.version}`} />
            </div>
          ) : (
            <p className="text-xs text-gray-400">Sin definicion de agente.</p>
          )}
        </div>
      </div>

      {/* Capabilities */}
      <div className="mt-4">
        <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Capacidades</h4>
        <div className="flex flex-wrap gap-2">
          {detail.capabilities.length === 0 ? (
            <p className="text-xs text-gray-400">Sin capacidades definidas.</p>
          ) : (
            detail.capabilities.map((cap) => (
              <span key={cap} className="text-xs px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700 font-medium">
                {cap}
              </span>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between">
      <span className="text-gray-500 text-xs">{label}</span>
      <span className={`text-gray-900 text-xs font-medium ${mono ? "font-mono" : ""} max-w-[60%] text-right truncate`}>
        {value}
      </span>
    </div>
  );
}
