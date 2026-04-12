import { useState, useMemo } from "react";
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
import {
  Activity,
  Sparkles,
  GitBranch,
  Target,
  ArrowUpRight,
} from "lucide-react";
import type {
  PromptVersion,
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
  general: "bg-[var(--neu-dark)]/10 text-[var(--text-secondary)]",
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
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Sparkles className="w-5 h-5 text-indigo-500" />
        <h1 className="text-xl font-bold text-[var(--text-primary)]">Prompt Engineering</h1>
      </div>

      {/* Tabs — neumorphic pressed container */}
      <div className="neu-pressed-sm flex gap-1 p-1 w-fit">
        <button
          onClick={() => setTab("templates")}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-all duration-200 ${
            tab === "templates"
              ? "neu-sm text-indigo-500"
              : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
          }`}
        >
          Biblioteca de Templates
        </button>
        <button
          onClick={() => setTab("versions")}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-all duration-200 ${
            tab === "versions"
              ? "neu-sm text-indigo-500"
              : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
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
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
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
          className="flex-1 max-w-xs rounded-md border border-[var(--neu-dark)]/30 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-md border border-[var(--neu-dark)]/30 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
                  <h3 className="text-sm font-semibold text-[var(--text-primary)] leading-tight">
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
                  <p className="text-xs text-[var(--text-muted)] line-clamp-2 mb-2">
                    {t.description}
                  </p>
                )}
                <div className="flex items-center gap-2 flex-wrap mb-2">
                  {t.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-xs bg-[var(--neu-dark)]/10 text-[var(--text-secondary)] px-2 py-0.5 rounded"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
                <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
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
                  <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
                    {t.model_provider && (
                      <span className="bg-[var(--neu-dark)]/10 px-2 py-0.5 rounded">
                        {t.model_provider}
                      </span>
                    )}
                    {t.model_name && (
                      <span className="bg-[var(--neu-dark)]/10 px-2 py-0.5 rounded">
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

  // Sorted by version number for the sparkline (ascending)
  const sortedVersions = useMemo(
    () => [...versions].sort((a, b) => a.version - b.version),
    [versions]
  );

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
        <label className="text-sm font-medium text-[var(--text-secondary)]">Agente:</label>
        <select
          value={selectedAgentId}
          onChange={(e) => {
            setSelectedAgentId(e.target.value);
            setShowEditor(false);
            resetCompare();
          }}
          className="flex-1 max-w-md rounded-xl neu-pressed-sm px-3 py-2 text-sm bg-transparent text-[var(--text-primary)] focus:outline-none"
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

      {/* Score Evolution Chart — shows when agent has versions with scores */}
      {selectedAgentId && !versionsLoading && sortedVersions.length > 0 && (
        <ScoreEvolutionChart versions={sortedVersions} />
      )}

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
          <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
            Crear Nueva Versión
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
                className="px-4 py-2 text-sm font-medium text-white bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-xl hover:from-indigo-600 hover:to-indigo-700 transition-all"
              >
                Crear Nueva Versión
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
              className={`px-4 py-2 text-sm font-medium rounded-xl transition-all ${
                compareMode
                  ? "bg-yellow-50 text-yellow-700 ring-2 ring-yellow-300"
                  : "neu-sm text-[var(--text-primary)]"
              }`}
            >
              {compareMode
                ? compareV1 === 0
                  ? "Selecciona la 1ra versión..."
                  : "Selecciona la 2da versión..."
                : "Comparar"}
            </button>
            <button
              onClick={() => setShowApplyTemplate(!showApplyTemplate)}
              className="px-4 py-2 text-sm font-medium neu-sm text-[var(--text-primary)] rounded-xl"
            >
              Aplicar Template
            </button>
          </div>

          {/* Version timeline */}
          {versions.length === 0 ? (
            <EmptyState
              title="Sin versiones"
              description="Este agente no tiene versiones de prompt aún. Crea la primera."
            />
          ) : (
            <div className="space-y-2">
              {versions.map((v) => (
                <div
                  key={v.id}
                  className={`neu-flat rounded-xl p-4 transition-all cursor-pointer ${
                    v.is_active ? "ring-2 ring-emerald-400/60" : ""
                  } ${
                    compareMode ? "hover:ring-2 hover:ring-yellow-400" : ""
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
                      {/* Version badge */}
                      <span className="flex items-center gap-1 text-sm font-bold text-[var(--text-primary)]">
                        <GitBranch className="w-3.5 h-3.5 text-indigo-400" />
                        v{v.version}
                      </span>
                      {v.is_active && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 font-semibold uppercase tracking-wider">
                          Activa
                        </span>
                      )}
                      {/* Color-coded score badge */}
                      {v.performance_score !== null && (
                        <ScoreBadge score={v.performance_score} />
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {!v.is_active && !compareMode && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleActivate(v.version);
                          }}
                          className="px-3 py-1 text-xs font-medium text-emerald-600 bg-emerald-50 rounded-lg hover:bg-emerald-100 transition-colors"
                        >
                          Activar
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-4 mt-1.5 text-xs text-[var(--text-muted)]">
                    {v.change_notes && (
                      <span className="text-[var(--text-secondary)]">{v.change_notes}</span>
                    )}
                    {v.created_by && <span>Por: {v.created_by}</span>}
                    <span>{formatRelative(v.created_at)}</span>
                  </div>

                  {/* Expanded version details */}
                  {expandedVersionId === v.id && !compareMode && (
                    <div className="mt-3 pt-3 border-t border-[var(--neu-dark)]/10 space-y-2">
                      <div className="bg-gray-900 text-green-400 font-mono text-xs p-3 rounded-lg max-h-64 overflow-y-auto whitespace-pre-wrap">
                        {v.system_prompt}
                      </div>
                      <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
                        {v.model_provider && (
                          <span className="neu-pressed-sm px-2 py-0.5 rounded">
                            {v.model_provider}
                          </span>
                        )}
                        {v.model_name && (
                          <span className="neu-pressed-sm px-2 py-0.5 rounded">
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

// ── Score Evolution Chart ──────────────────────────────────
// SVG sparkline showing how performance_score improves across versions.
// Highlights the active version and shows improvement delta.

function ScoreEvolutionChart({ versions }: { versions: PromptVersion[] }) {
  const scored = versions.filter((v) => v.performance_score !== null);
  if (scored.length === 0) return null;

  const scores = scored.map((v) => v.performance_score!);
  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);

  // Compute improvement from first to last scored version
  const firstScore = scores[0] ?? 0;
  const lastScore = scores[scores.length - 1] ?? 0;
  const improvement = scores.length >= 2 ? lastScore - firstScore : 0;
  const improvementPct = firstScore > 0 ? ((improvement / firstScore) * 100).toFixed(0) : "0";

  // Active version score
  const activeVersion = versions.find((v) => v.is_active);
  const activeScore = activeVersion?.performance_score;

  // SVG dimensions — responsive-friendly
  const W = 280;
  const H = 60;
  const PAD = 12;

  // Map score to Y coordinate (inverted — higher score = lower Y)
  const rangeY = maxScore - minScore || 1; // avoid division by zero for single score
  const toY = (s: number) => PAD + (1 - (s - minScore) / rangeY) * (H - 2 * PAD);
  const toX = (i: number) =>
    scored.length === 1
      ? W / 2
      : PAD + (i / (scored.length - 1)) * (W - 2 * PAD);

  // Build polyline points — use v.performance_score! since we filtered nulls
  const points = scored.map((v, i) => `${toX(i)},${toY(v.performance_score!)}`).join(" ");

  // Gradient ID — unique color based on improvement direction
  const isPositive = improvement >= 0;

  return (
    <div className="neu-flat rounded-xl p-5">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-indigo-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-indigo-500">
            Evolución de Score
          </h3>
        </div>
        <div className="flex items-center gap-4">
          {activeScore !== null && activeScore !== undefined && (
            <div className="text-right">
              <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">Score Activo</p>
              <p className="text-lg font-bold text-[var(--text-primary)]">{activeScore.toFixed(1)}</p>
            </div>
          )}
          {scores.length >= 2 && (
            <div className="text-right">
              <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">Mejora</p>
              <p className={`text-lg font-bold flex items-center gap-0.5 ${isPositive ? "text-emerald-500" : "text-red-400"}`}>
                <ArrowUpRight className={`w-4 h-4 ${isPositive ? "" : "rotate-90"}`} />
                +{improvement.toFixed(1)}
                <span className="text-xs font-medium ml-0.5">({improvementPct}%)</span>
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Sparkline SVG */}
      <div className="neu-pressed rounded-lg p-3">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-16" preserveAspectRatio="none">
          {/* Gradient fill under the line */}
          <defs>
            <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={isPositive ? "#6366f1" : "#ef4444"} stopOpacity="0.3" />
              <stop offset="100%" stopColor={isPositive ? "#6366f1" : "#ef4444"} stopOpacity="0.02" />
            </linearGradient>
          </defs>

          {/* Fill area */}
          {scored.length >= 2 && (
            <polygon
              points={`${toX(0)},${H - PAD} ${points} ${toX(scored.length - 1)},${H - PAD}`}
              fill="url(#scoreGrad)"
            />
          )}

          {/* Line */}
          <polyline
            points={points}
            fill="none"
            stroke={isPositive ? "#6366f1" : "#ef4444"}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Dots for each version */}
          {scored.map((v, i) => {
            const isActive = v.is_active;
            const score = v.performance_score!;
            return (
              <g key={v.id}>
                {/* Outer glow for active version */}
                {isActive && (
                  <circle
                    cx={toX(i)}
                    cy={toY(score)}
                    r="7"
                    fill="none"
                    stroke="#10b981"
                    strokeWidth="1.5"
                    opacity="0.5"
                  />
                )}
                <circle
                  cx={toX(i)}
                  cy={toY(score)}
                  r={isActive ? "4" : "3"}
                  fill={isActive ? "#10b981" : isPositive ? "#6366f1" : "#ef4444"}
                />
                {/* Score label above dot */}
                <text
                  x={toX(i)}
                  y={toY(score) - 8}
                  textAnchor="middle"
                  className="text-[8px] fill-[var(--text-muted)]"
                  style={{ fontSize: "8px" }}
                >
                  {score.toFixed(1)}
                </text>
                {/* Version label below dot */}
                <text
                  x={toX(i)}
                  y={H - 2}
                  textAnchor="middle"
                  className="text-[7px] fill-[var(--text-muted)]"
                  style={{ fontSize: "7px" }}
                >
                  v{v.version}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

// ── Score Badge ─────────────────────────────────────────────
// Color-coded: <6 red, 6-7.9 yellow/amber, 8+ green. Visual indicator for demo.

function ScoreBadge({ score }: { score: number }) {
  let colorClass: string;
  let bgClass: string;

  if (score >= 8) {
    colorClass = "text-emerald-700";
    bgClass = "bg-emerald-50";
  } else if (score >= 6) {
    colorClass = "text-amber-700";
    bgClass = "bg-amber-50";
  } else {
    colorClass = "text-red-700";
    bgClass = "bg-red-50";
  }

  return (
    <span className={`flex items-center gap-1 text-xs font-semibold ${colorClass} ${bgClass} px-2 py-0.5 rounded-full`}>
      <Target className="w-3 h-3" />
      {score.toFixed(1)}
    </span>
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
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">
          Aplicar Template al Agente
        </h3>
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-sm text-[var(--text-secondary)] bg-[var(--neu-dark)]/10 rounded-md hover:bg-[var(--neu-dark)]/20"
        >
          Cerrar
        </button>
      </div>

      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Buscar templates..."
        className="w-full max-w-xs rounded-md border border-[var(--neu-dark)]/30 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />

      {isLoading && <LoadingSpinner />}

      {!isLoading && templates.length === 0 && (
        <p className="text-sm text-[var(--text-muted)]">No se encontraron templates.</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-64 overflow-y-auto">
        {templates.map((t) => (
          <div
            key={t.id}
            className="flex items-center justify-between p-3 bg-[var(--neu-bg)] rounded-lg border hover:border-indigo-300"
          >
            <div className="min-w-0">
              <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                {t.name}
              </p>
              <p className="text-xs text-[var(--text-muted)]">
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
