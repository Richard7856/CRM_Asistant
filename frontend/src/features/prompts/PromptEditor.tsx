import { useState, useEffect } from "react";
import type { CreatePromptVersion, CreatePromptTemplate, PromptVersion, PromptTemplate } from "@/types/prompt";

interface PromptEditorProps {
  mode: "version" | "template";
  initial?: Partial<PromptVersion | PromptTemplate> | null;
  onSave: (data: CreatePromptVersion | CreatePromptTemplate) => void;
  onCancel: () => void;
  saving?: boolean;
}

export default function PromptEditor({ mode, initial, onSave, onCancel, saving }: PromptEditorProps) {
  const [systemPrompt, setSystemPrompt] = useState(initial?.system_prompt ?? "");
  const [modelProvider, setModelProvider] = useState(initial?.model_provider ?? "");
  const [modelName, setModelName] = useState(initial?.model_name ?? "");
  const [temperature, setTemperature] = useState(initial?.temperature ?? 0.7);
  const [maxTokens, setMaxTokens] = useState(initial?.max_tokens ?? 4096);
  const [toolsJson, setToolsJson] = useState(
    initial?.tools?.length ? JSON.stringify(initial.tools, null, 2) : "[]"
  );
  const [changeNotes, setChangeNotes] = useState("");

  // template-only fields
  const [name, setName] = useState((initial as any)?.name ?? "");
  const [description, setDescription] = useState((initial as any)?.description ?? "");
  const [category, setCategory] = useState((initial as any)?.category ?? "general");
  const [tagsText, setTagsText] = useState(
    ((initial as any)?.tags ?? []).join(", ")
  );

  useEffect(() => {
    if (initial) {
      setSystemPrompt(initial.system_prompt ?? "");
      setModelProvider(initial.model_provider ?? "");
      setModelName(initial.model_name ?? "");
      setTemperature(initial.temperature ?? 0.7);
      setMaxTokens(initial.max_tokens ?? 4096);
      setToolsJson(initial.tools?.length ? JSON.stringify(initial.tools, null, 2) : "[]");
      if (mode === "template") {
        setName((initial as any).name ?? "");
        setDescription((initial as any).description ?? "");
        setCategory((initial as any).category ?? "general");
        setTagsText(((initial as any).tags ?? []).join(", "));
      }
    }
  }, [initial, mode]);

  const charCount = systemPrompt.length;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    let tools: any[] = [];
    try {
      tools = JSON.parse(toolsJson);
    } catch {
      // keep empty
    }

    if (mode === "template") {
      const tags = tagsText
        .split(",")
        .map((s: string) => s.trim())
        .filter(Boolean);
      const payload: CreatePromptTemplate = {
        name,
        description: description || undefined,
        category,
        system_prompt: systemPrompt,
        model_provider: modelProvider || undefined,
        model_name: modelName || undefined,
        temperature,
        max_tokens: maxTokens,
        tools: tools.length ? tools : undefined,
        tags: tags.length ? tags : undefined,
      };
      onSave(payload);
    } else {
      const payload: CreatePromptVersion = {
        system_prompt: systemPrompt,
        model_provider: modelProvider || undefined,
        model_name: modelName || undefined,
        temperature,
        max_tokens: maxTokens,
        tools: tools.length ? tools : undefined,
        change_notes: changeNotes || undefined,
      };
      onSave(payload);
    }
  }

  const CATEGORIES = [
    { value: "marketing", label: "Marketing" },
    { value: "ventas", label: "Ventas" },
    { value: "soporte", label: "Soporte" },
    { value: "analytics", label: "Analytics" },
    { value: "general", label: "General" },
  ];

  const PROVIDERS = [
    { value: "", label: "-- Ninguno --" },
    { value: "anthropic", label: "Anthropic" },
    { value: "openai", label: "OpenAI" },
    { value: "google", label: "Google" },
  ];

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {mode === "template" && (
        <>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Nombre
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Categoria
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Descripcion
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Tags (separados por coma)
            </label>
            <input
              type="text"
              value={tagsText}
              onChange={(e) => setTagsText(e.target.value)}
              placeholder="ej: chatbot, email, crm"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </>
      )}

      {/* System Prompt */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="block text-sm font-medium text-gray-700">
            System Prompt
          </label>
          <span className="text-xs text-gray-400">{charCount} caracteres</span>
        </div>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          required
          rows={12}
          className="w-full rounded-md bg-gray-900 text-green-400 font-mono text-sm px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
          placeholder="Eres un asistente que..."
        />
      </div>

      {/* Model config */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Proveedor del modelo
          </label>
          <select
            value={modelProvider}
            onChange={(e) => setModelProvider(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Nombre del modelo
          </label>
          <input
            type="text"
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
            placeholder="ej: gpt-4o, claude-3-opus"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Temperatura: {temperature.toFixed(2)}
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={temperature}
            onChange={(e) => setTemperature(parseFloat(e.target.value))}
            className="w-full accent-indigo-600"
          />
          <div className="flex justify-between text-xs text-gray-400">
            <span>0 (preciso)</span>
            <span>1 (creativo)</span>
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Max Tokens
          </label>
          <input
            type="number"
            min={1}
            max={200000}
            value={maxTokens}
            onChange={(e) => setMaxTokens(parseInt(e.target.value) || 4096)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
      </div>

      {/* Tools */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Tools (JSON)
        </label>
        <textarea
          value={toolsJson}
          onChange={(e) => setToolsJson(e.target.value)}
          rows={4}
          className="w-full rounded-md bg-gray-900 text-green-400 font-mono text-xs px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
        />
      </div>

      {/* Change notes for versions */}
      {mode === "version" && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Notas del cambio
          </label>
          <input
            type="text"
            value={changeNotes}
            onChange={(e) => setChangeNotes(e.target.value)}
            placeholder="Describe los cambios realizados..."
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <button
          type="submit"
          disabled={saving || !systemPrompt.trim()}
          className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? "Guardando..." : "Guardar"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-gray-700 neu-sm border border-[var(--neu-dark)] rounded-md hover:bg-[var(--neu-dark)]/20"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
