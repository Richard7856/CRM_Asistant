import { useState } from "react";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import EmptyState from "@/components/common/EmptyState";
import {
  useTemplates,
  useCreateTemplate,
  useUpdateTemplate,
  useDeleteTemplate,
  useVersions,
  useCreateVersion,
  useActivateVersion,
  useApplyTemplate,
} from "@/hooks/usePrompts";
import { useAgents } from "@/hooks/useAgents";
import { formatRelative } from "@/lib/formatters";
import PromptEditor from "./PromptEditor";
import PromptCompareView from "./PromptCompareView";
import type {
  PromptTemplate,
  CreatePromptTemplate,
  CreatePromptVersion,
} from "@/types/prompt";

// ── Constants ──────────────────────────────────────────────

const CATEGORY_COLORS: Record<string, string> = {
  marketing: "bg-purple-100 text-purple-700",
  ventas: "bg-blue-100 text-blue-700",
  soporte: "bg-green-100 text-green-700",
  analytics: "bg-orange-100 text-orange-700",
  general: "bg-gray-100 text-gray-700",
};

const CATEGORY_OPTIONS = [
  { value: "", label: "Todas" },
  { value: "marketing", label: "Marketing" },
  { value: "ventas", label: "Ventas" },
  { value: "soporte", label: "Soporte" },
  { value: "analytics", label: "Analytics" },
  { value: "general", label: "General" },
];

type Tab = "templates" | "versions";

// ── Main Page ──────────────────────────────────────────────

export default function PromptEngineeringPage() {
  const [tab, setTab] = useState<Tab>("templates");

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Prompt Engineering</h1>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        <button
          onClick={() => setTab("templates")}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            tab === "templates"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Biblioteca de Templates
        </button>
        <button
          onClick={() => setTab("versions")}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            tab === "versions"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Versiones por Agente
        </button>
      </div>

      {tab === "templates" ? <TemplatesTab /> : <VersionsTab />}
    </div>
  );
}

// ── Templates Tab ──────────────────────────────────────────

function TemplatesTab() {
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [showEditor, setShowEditor] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<PromptTemplate | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data, isLoading } = useTemplates({
    category: category || undefined,
    search: search || undefined,
    page: 1,
    size: 50,
  });

  const createMutation = useCreateTemplate();
  const updateMutation = useUpdateTemplate();
  const deleteMutation = useDeleteTemplate();

  function handleSaveTemplate(payload: CreatePromptTemplate | CreatePromptVersion) {
    const templateData = payload as CreatePromptTemplate;
    if (editingTemplate) {
      updateMutation.mutate(
        { id: editingTemplate.id, updates: templateData },
        {
          onSuccess: () => {
            setShowEditor(false);
            setEditingTemplate(null);
          },
        }
      );
    } else {
      createMutation.mutate(templateData, {
        onSuccess: () => {
          setShowEditor(false);
        },
      });
    }
  }

  function handleEdit(template: PromptTemplate) {
    setEditingTemplate(template);
    setShowEditor(true);
  }

  function handleDelete(template: PromptTemplate) {
    if (window.confirm(`Eliminar template "${template.name}"?`)) {
      deleteMutation.mutate(template.id);
    }
  }

  if (isLoading) return <LoadingSpinner />;

  if (showEditor) {
    return (
      <div className="neu-flat rounded-xl p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          {editingTemplate ? "Editar Template" : "Crear Template"}
        </h2>
        <PromptEditor
          mode="template"
          initial={editingTemplate}
          onSave={handleSaveTemplate}
          onCancel={() => {
            setShowEditor(false);
            setEditingTemplate(null);
          }}
          saving={createMutation.isPending || updateMutation.isPending}
        />
      </div>
    );
  }

  const templates = data?.items ?? [];

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar templates..."
          className="flex-1 max-w-xs rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {CATEGORY_OPTIONS.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
        <button
          onClick={() => {
            setEditingTemplate(null);
            setShowEditor(true);
          }}
          className="ml-auto px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
        >
          Crear Template
        </button>
      </div>

      {/* Template Grid */}
      {templates.length === 0 ? (
        <EmptyState
          title="No hay templates"
          description="Crea tu primer template para comenzar."
          action={
            <button
              onClick={() => setShowEditor(true)}
              className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
            >
              Crear Template
            </button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((t) => (
            <div key={t.id} className="neu-flat rounded-xl hover:shadow-md transition-shadow">
              <div
                className="p-4 cursor-pointer"
                onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
              >
                <div className="flex items-start justify-between mb-2">
                  <h3 className="text-sm font-semibold text-gray-900 leading-tight">
                    {t.name}
                  </h3>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      CATEGORY_COLORS[t.category] ?? CATEGORY_COLORS.general
                    }`}
                  >
                    {t.category}
                  </span>
                </div>
                {t.description && (
                  <p className="text-xs text-gray-500 line-clamp-2 mb-2">
                    {t.description}
                  </p>
                )}
                <div className="flex items-center gap-2 flex-wrap mb-2">
                  {t.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
                <div className="flex items-center justify-between text-xs text-gray-400">
                  <span>Usos: {t.usage_count}</span>
                  <span>{formatRelative(t.created_at)}</span>
                </div>
              </div>

              {/* Expanded view */}
              {expandedId === t.id && (
                <div className="border-t px-4 py-3 space-y-3">
                  <div className="bg-gray-900 text-green-400 font-mono text-xs p-3 rounded-lg max-h-48 overflow-y-auto whitespace-pre-wrap">
                    {t.system_prompt}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    {t.model_provider && (
                      <span className="bg-gray-100 px-2 py-0.5 rounded">
                        {t.model_provider}
                      </span>
                    )}
                    {t.model_name && (
                      <span className="bg-gray-100 px-2 py-0.5 rounded">
                        {t.model_name}
                      </span>
                    )}
                    <span>Temp: {t.temperature}</span>
                    <span>Max: {t.max_tokens}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleEdit(t);
                      }}
                      className="px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-md hover:bg-indigo-100"
                    >
                      Editar
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(t);
                      }}
                      className="px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 rounded-md hover:bg-red-100"
                    >
                      Eliminar
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Versions Tab ───────────────────────────────────────────

function VersionsTab() {
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [showEditor, setShowEditor] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [compareV1, setCompareV1] = useState(0);
  const [compareV2, setCompareV2] = useState(0);
  const [showCompare, setShowCompare] = useState(false);
  const [showApplyTemplate, setShowApplyTemplate] = useState(false);
  const [expandedVersionId, setExpandedVersionId] = useState<string | null>(null);

  const { data: agentsData, isLoading: agentsLoading } = useAgents({ page: 1, size: 100 });
  const { data: versionsData, isLoading: versionsLoading } = useVersions(
    selectedAgentId || undefined,
    { page: 1, size: 50 }
  );

  const createVersionMutation = useCreateVersion();
  const activateMutation = useActivateVersion();
  const applyTemplateMutation = useApplyTemplate();

  const agents = agentsData?.items ?? [];
  const versions = versionsData?.items ?? [];

  function handleCreateVersion(payload: CreatePromptVersion | CreatePromptTemplate) {
    const versionData = payload as CreatePromptVersion;
    createVersionMutation.mutate(
      { agentId: selectedAgentId, data: versionData },
      { onSuccess: () => setShowEditor(false) }
    );
  }

  function handleActivate(version: number) {
    activateMutation.mutate({ agentId: selectedAgentId, version });
  }

  function handleCompareSelect(version: number) {
    if (compareV1 === 0) {
      setCompareV1(version);
    } else if (compareV2 === 0 && version !== compareV1) {
      setCompareV2(version);
      setShowCompare(true);
      setCompareMode(false);
    }
  }

  function resetCompare() {
    setCompareV1(0);
    setCompareV2(0);
    setShowCompare(false);
    setCompareMode(false);
  }

  // Find active version to pre-fill editor
  const activeVersion = versions.find((v) => v.is_active);

  if (agentsLoading) return <LoadingSpinner />;

  return (
    <div className="space-y-4">
      {/* Agent selector */}
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-gray-700">Agente:</label>
        <select
          value={selectedAgentId}
          onChange={(e) => {
            setSelectedAgentId(e.target.value);
            setShowEditor(false);
            resetCompare();
          }}
          className="flex-1 max-w-md rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">-- Seleccionar agente --</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </div>

      {!selectedAgentId && (
        <EmptyState
          title="Selecciona un agente"
          description="Elige un agente para ver y gestionar sus versiones de prompt."
        />
      )}

      {selectedAgentId && versionsLoading && <LoadingSpinner />}

      {/* Compare view */}
      {selectedAgentId && showCompare && (
        <PromptCompareView
          agentId={selectedAgentId}
          v1={compareV1}
          v2={compareV2}
          onClose={resetCompare}
        />
      )}

      {/* Apply Template modal */}
      {selectedAgentId && showApplyTemplate && (
        <ApplyTemplatePanel
          onApply={(templateId) => {
            applyTemplateMutation.mutate(
              { agentId: selectedAgentId, templateId },
              { onSuccess: () => setShowApplyTemplate(false) }
            );
          }}
          onClose={() => setShowApplyTemplate(false)}
          applying={applyTemplateMutation.isPending}
        />
      )}

      {/* Editor */}
      {selectedAgentId && showEditor && (
        <div className="neu-flat rounded-xl p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Crear Nueva Version
          </h2>
          <PromptEditor
            mode="version"
            initial={activeVersion}
            onSave={handleCreateVersion}
            onCancel={() => setShowEditor(false)}
            saving={createVersionMutation.isPending}
          />
        </div>
      )}

      {/* Versions list */}
      {selectedAgentId && !versionsLoading && !showCompare && (
        <div className="space-y-3">
          {/* Toolbar */}
          <div className="flex items-center gap-2 flex-wrap">
            {!showEditor && (
              <button
                onClick={() => setShowEditor(true)}
                className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
              >
                Crear Nueva Version
              </button>
            )}
            <button
              onClick={() => {
                if (compareMode) {
                  resetCompare();
                } else {
                  setCompareMode(true);
                  setCompareV1(0);
                  setCompareV2(0);
                }
              }}
              className={`px-4 py-2 text-sm font-medium rounded-md border ${
                compareMode
                  ? "bg-yellow-50 text-yellow-700 border-yellow-300"
                  : "text-[var(--text-primary)] neu-sm border-[var(--neu-dark)] hover:bg-[var(--neu-dark)]/20"
              }`}
            >
              {compareMode
                ? compareV1 === 0
                  ? "Selecciona la 1ra version..."
                  : "Selecciona la 2da version..."
                : "Comparar"}
            </button>
            <button
              onClick={() => setShowApplyTemplate(!showApplyTemplate)}
              className="px-4 py-2 text-sm font-medium text-gray-700 neu-sm border border-[var(--neu-dark)] rounded-md hover:bg-[var(--neu-dark)]/20"
            >
              Aplicar Template
            </button>
          </div>

          {/* Version timeline */}
          {versions.length === 0 ? (
            <EmptyState
              title="Sin versiones"
              description="Este agente no tiene versiones de prompt aun. Crea la primera."
            />
          ) : (
            <div className="space-y-2">
              {versions.map((v) => (
                <div
                  key={v.id}
                  className={`neu-flat rounded-xl p-4 transition-all ${
                    v.is_active ? "ring-2 ring-green-500 border-green-300" : ""
                  } ${
                    compareMode ? "cursor-pointer hover:ring-2 hover:ring-yellow-400" : ""
                  } ${
                    compareV1 === v.version ? "ring-2 ring-yellow-400" : ""
                  }`}
                  onClick={() => {
                    if (compareMode) {
                      handleCompareSelect(v.version);
                    } else {
                      setExpandedVersionId(expandedVersionId === v.id ? null : v.id);
                    }
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-bold text-gray-900">
                        v{v.version}
                      </span>
                      {v.is_active && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">
                          Activa
                        </span>
                      )}
                      {v.performance_score !== null && (
                        <span className="text-xs text-gray-500">
                          Score: {v.performance_score.toFixed(1)}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {!v.is_active && !compareMode && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleActivate(v.version);
                          }}
                          className="px-3 py-1 text-xs font-medium text-green-700 bg-green-50 rounded-md hover:bg-green-100"
                        >
                          Activar
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-4 mt-1 text-xs text-gray-400">
                    {v.change_notes && (
                      <span className="text-gray-600">{v.change_notes}</span>
                    )}
                    {v.created_by && <span>Por: {v.created_by}</span>}
                    <span>{formatRelative(v.created_at)}</span>
                  </div>

                  {/* Expanded version details */}
                  {expandedVersionId === v.id && !compareMode && (
                    <div className="mt-3 pt-3 border-t space-y-2">
                      <div className="bg-gray-900 text-green-400 font-mono text-xs p-3 rounded-lg max-h-64 overflow-y-auto whitespace-pre-wrap">
                        {v.system_prompt}
                      </div>
                      <div className="flex items-center gap-2 text-xs text-gray-500">
                        {v.model_provider && (
                          <span className="bg-gray-100 px-2 py-0.5 rounded">
                            {v.model_provider}
                          </span>
                        )}
                        {v.model_name && (
                          <span className="bg-gray-100 px-2 py-0.5 rounded">
                            {v.model_name}
                          </span>
                        )}
                        <span>Temp: {v.temperature}</span>
                        <span>Max: {v.max_tokens}</span>
                        {v.tools.length > 0 && (
                          <span>Tools: {v.tools.length}</span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Apply Template Panel ───────────────────────────────────

function ApplyTemplatePanel({
  onApply,
  onClose,
  applying,
}: {
  onApply: (templateId: string) => void;
  onClose: () => void;
  applying: boolean;
}) {
  const [search, setSearch] = useState("");
  const { data, isLoading } = useTemplates({
    search: search || undefined,
    page: 1,
    size: 20,
  });

  const templates = data?.items ?? [];

  return (
    <div className="neu-flat rounded-xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">
          Aplicar Template al Agente
        </h3>
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-sm text-gray-600 bg-gray-100 rounded-md hover:bg-gray-200"
        >
          Cerrar
        </button>
      </div>

      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Buscar templates..."
        className="w-full max-w-xs rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />

      {isLoading && <LoadingSpinner />}

      {!isLoading && templates.length === 0 && (
        <p className="text-sm text-gray-500">No se encontraron templates.</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-64 overflow-y-auto">
        {templates.map((t) => (
          <div
            key={t.id}
            className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border hover:border-indigo-300"
          >
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">
                {t.name}
              </p>
              <p className="text-xs text-gray-500">
                {t.category} &middot; Usos: {t.usage_count}
              </p>
            </div>
            <button
              onClick={() => onApply(t.id)}
              disabled={applying}
              className="ml-3 shrink-0 px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-md hover:bg-indigo-100 disabled:opacity-50"
            >
              Aplicar
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
