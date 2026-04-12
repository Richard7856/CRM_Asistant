/**
 * Admin Credentials Page — CRUD for API keys and secrets.
 *
 * Secrets are write-only: the backend never returns the full value,
 * only a masked preview (****xxxx). This page lets admins create,
 * toggle, and delete credentials used by agents for MCP tool execution.
 */

import { useState } from "react";
import {
  useCredentials,
  useCreateCredential,
  useUpdateCredential,
  useDeleteCredential,
} from "@/hooks/useCredentials";
import { useAgents } from "@/hooks/useAgents";
import { useToastStore } from "@/stores/toastStore";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import EmptyState from "@/components/common/EmptyState";
import { formatRelative } from "@/lib/formatters";
import {
  Key,
  Plus,
  Trash2,
  Shield,
  ShieldOff,
  Eye,
  EyeOff,
  Bot,
  Server,
  X,
} from "lucide-react";
import type { Credential, CreateCredential, CredentialType } from "@/types/credential";

const CREDENTIAL_TYPE_LABELS: Record<CredentialType, string> = {
  api_key: "API Key",
  oauth_token: "OAuth Token",
  bearer_token: "Bearer Token",
  basic_auth: "Basic Auth",
  custom: "Custom",
};

const CREDENTIAL_TYPE_OPTIONS: CredentialType[] = [
  "api_key",
  "oauth_token",
  "bearer_token",
  "basic_auth",
  "custom",
];

// Common services for quick selection in the form
const SERVICE_PRESETS = [
  "anthropic",
  "openai",
  "serper",
  "slack",
  "github",
  "google",
  "notion",
  "custom",
];

export default function CredentialsPage() {
  const [showForm, setShowForm] = useState(false);
  const [filterService, setFilterService] = useState("");
  const addToast = useToastStore((s) => s.addToast);

  const { data, isLoading } = useCredentials({
    page: 1,
    size: 50,
    service_name: filterService || undefined,
  });

  const deleteMutation = useDeleteCredential();
  const updateMutation = useUpdateCredential();

  const handleToggleActive = (cred: Credential) => {
    updateMutation.mutate(
      { id: cred.id, data: { is_active: !cred.is_active } },
      {
        onSuccess: () => {
          addToast({
            type: "success",
            title: cred.is_active ? "Credencial desactivada" : "Credencial activada",
            message: cred.name,
          });
        },
      }
    );
  };

  const handleDelete = (cred: Credential) => {
    if (!window.confirm(`¿Eliminar credencial "${cred.name}"? Esta acción no se puede deshacer.`)) return;
    deleteMutation.mutate(cred.id, {
      onSuccess: () => {
        addToast({ type: "success", title: "Eliminada", message: cred.name });
      },
    });
  };

  if (isLoading) return <LoadingSpinner />;

  const credentials = data?.items ?? [];

  // Collect unique service names for the filter
  const serviceNames = [...new Set(credentials.map((c) => c.service_name))].sort();

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Key className="w-5 h-5 text-indigo-500" />
          <h1 className="text-xl font-bold text-[var(--text-primary)]">Credenciales</h1>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-xl hover:from-indigo-600 hover:to-indigo-700 transition-all"
        >
          <Plus className="w-4 h-4" />
          Nueva Credencial
        </button>
      </div>

      {/* Filter bar */}
      {serviceNames.length > 1 && (
        <div className="neu-pressed-sm flex gap-1 p-1 w-fit">
          <button
            onClick={() => setFilterService("")}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
              !filterService
                ? "neu-sm text-indigo-500"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            }`}
          >
            Todas
          </button>
          {serviceNames.map((svc) => (
            <button
              key={svc}
              onClick={() => setFilterService(svc)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                filterService === svc
                  ? "neu-sm text-indigo-500"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              {svc}
            </button>
          ))}
        </div>
      )}

      {/* Create form */}
      {showForm && (
        <CreateCredentialForm
          onClose={() => setShowForm(false)}
          onCreated={() => {
            setShowForm(false);
            addToast({ type: "success", title: "Credencial creada", message: "Lista para usar" });
          }}
        />
      )}

      {/* Credential list */}
      {credentials.length === 0 ? (
        <EmptyState
          title="Sin credenciales"
          description="Agrega API keys y tokens para que tus agentes puedan usar herramientas externas."
          action={
            <button
              onClick={() => setShowForm(true)}
              className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"
            >
              Crear primera credencial
            </button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {credentials.map((cred) => (
            <CredentialCard
              key={cred.id}
              credential={cred}
              onToggle={() => handleToggleActive(cred)}
              onDelete={() => handleDelete(cred)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Credential Card ───────────────────────────────────────

function CredentialCard({
  credential: cred,
  onToggle,
  onDelete,
}: {
  credential: Credential;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const [showPreview, setShowPreview] = useState(false);

  return (
    <div
      className={`neu-flat rounded-xl p-4 transition-all ${
        !cred.is_active ? "opacity-60" : ""
      }`}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className={`p-1.5 rounded-lg ${cred.is_active ? "bg-indigo-50" : "bg-[var(--neu-dark)]/10"}`}>
            <Key className={`w-4 h-4 ${cred.is_active ? "text-indigo-500" : "text-[var(--text-muted)]"}`} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)] truncate">
              {cred.name}
            </p>
            <p className="text-[11px] text-[var(--text-muted)]">
              {CREDENTIAL_TYPE_LABELS[cred.credential_type]}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={onToggle}
            className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            title={cred.is_active ? "Desactivar" : "Activar"}
          >
            {cred.is_active ? (
              <Shield className="w-3.5 h-3.5 text-emerald-500" />
            ) : (
              <ShieldOff className="w-3.5 h-3.5 text-[var(--text-muted)]" />
            )}
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-red-500 transition-colors"
            title="Eliminar"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Service + secret preview */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Server className="w-3 h-3 text-[var(--text-muted)]" />
          <span className="text-xs font-medium text-[var(--text-secondary)]">
            {cred.service_name}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPreview(!showPreview)}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            {showPreview ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
          </button>
          <code className="text-xs font-mono neu-pressed-sm px-2 py-1 rounded text-[var(--text-secondary)]">
            {showPreview ? cred.secret_preview : "••••••••"}
          </code>
        </div>

        {cred.agent_name && (
          <div className="flex items-center gap-1.5">
            <Bot className="w-3 h-3 text-[var(--text-muted)]" />
            <span className="text-[11px] text-[var(--text-muted)]">
              Asignada a: <span className="font-medium text-[var(--text-secondary)]">{cred.agent_name}</span>
            </span>
          </div>
        )}
        {!cred.agent_name && (
          <span className="text-[11px] text-[var(--text-muted)] italic">
            Compartida (todos los agentes)
          </span>
        )}
      </div>

      {/* Footer */}
      <div className="mt-3 pt-2 border-t border-[var(--neu-dark)]/10 flex items-center justify-between text-[10px] text-[var(--text-muted)]">
        <span>{formatRelative(cred.updated_at)}</span>
        {cred.notes && <span className="truncate max-w-[60%]">{cred.notes}</span>}
      </div>
    </div>
  );
}

// ── Create Credential Form ────────────────────────────────

function CreateCredentialForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [credType, setCredType] = useState<CredentialType>("api_key");
  const [secretValue, setSecretValue] = useState("");
  const [serviceName, setServiceName] = useState("");
  const [agentId, setAgentId] = useState("");
  const [notes, setNotes] = useState("");
  const [showSecret, setShowSecret] = useState(false);

  const createMutation = useCreateCredential();
  const { data: agentsData } = useAgents({ page: 1, size: 100 });
  const agents = agentsData?.items ?? [];

  const isValid = name.trim() && secretValue.trim() && serviceName.trim();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;

    const payload: CreateCredential = {
      name: name.trim(),
      credential_type: credType,
      secret_value: secretValue.trim(),
      service_name: serviceName.trim(),
      agent_id: agentId || null,
      notes: notes.trim() || undefined,
    };

    createMutation.mutate(payload, { onSuccess: onCreated });
  };

  return (
    <form onSubmit={handleSubmit} className="neu-flat rounded-xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
          Nueva Credencial
        </h2>
        <button type="button" onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Name */}
        <div>
          <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Nombre</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Mi API Key de OpenAI"
            className="mt-1 w-full neu-pressed-sm rounded-lg px-3 py-2 text-sm bg-transparent text-[var(--text-primary)] placeholder:text-[var(--text-muted)]/50 focus:outline-none"
          />
        </div>

        {/* Type */}
        <div>
          <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Tipo</label>
          <select
            value={credType}
            onChange={(e) => setCredType(e.target.value as CredentialType)}
            className="mt-1 w-full neu-pressed-sm rounded-lg px-3 py-2 text-sm bg-transparent text-[var(--text-primary)] focus:outline-none"
          >
            {CREDENTIAL_TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>{CREDENTIAL_TYPE_LABELS[t]}</option>
            ))}
          </select>
        </div>

        {/* Service */}
        <div>
          <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Servicio</label>
          <div className="mt-1 space-y-2">
            <input
              value={serviceName}
              onChange={(e) => setServiceName(e.target.value)}
              placeholder="anthropic"
              className="w-full neu-pressed-sm rounded-lg px-3 py-2 text-sm bg-transparent text-[var(--text-primary)] placeholder:text-[var(--text-muted)]/50 focus:outline-none"
            />
            <div className="flex flex-wrap gap-1">
              {SERVICE_PRESETS.map((svc) => (
                <button
                  key={svc}
                  type="button"
                  onClick={() => setServiceName(svc)}
                  className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                    serviceName === svc
                      ? "bg-indigo-100 text-indigo-700 font-medium"
                      : "bg-[var(--neu-bg)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                  }`}
                >
                  {svc}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Agent assignment */}
        <div>
          <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Agente (opcional)</label>
          <select
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            className="mt-1 w-full neu-pressed-sm rounded-lg px-3 py-2 text-sm bg-transparent text-[var(--text-primary)] focus:outline-none"
          >
            <option value="">Compartida (todos los agentes)</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Secret value — full width, masked input */}
      <div>
        <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Valor Secreto</label>
        <div className="mt-1 flex items-center gap-2">
          <input
            type={showSecret ? "text" : "password"}
            value={secretValue}
            onChange={(e) => setSecretValue(e.target.value)}
            placeholder="sk-..."
            className="flex-1 neu-pressed-sm rounded-lg px-3 py-2 text-sm font-mono bg-transparent text-[var(--text-primary)] placeholder:text-[var(--text-muted)]/50 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => setShowSecret(!showSecret)}
            className="p-2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          >
            {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Notes */}
      <div>
        <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Notas (opcional)</label>
        <input
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Cuenta de producción, límite $50/mes"
          className="mt-1 w-full neu-pressed-sm rounded-lg px-3 py-2 text-sm bg-transparent text-[var(--text-primary)] placeholder:text-[var(--text-muted)]/50 focus:outline-none"
        />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <button
          type="submit"
          disabled={!isValid || createMutation.isPending}
          className="px-5 py-2 text-sm font-medium text-white bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-xl hover:from-indigo-600 hover:to-indigo-700 disabled:opacity-50 transition-all"
        >
          {createMutation.isPending ? "Guardando..." : "Crear Credencial"}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="px-4 py-2 text-sm font-medium text-[var(--text-secondary)] neu-sm rounded-xl"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
