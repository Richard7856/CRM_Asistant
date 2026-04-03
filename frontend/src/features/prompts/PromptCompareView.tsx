import { useCompareVersions } from "@/hooks/usePrompts";
import LoadingSpinner from "@/components/common/LoadingSpinner";

interface PromptCompareViewProps {
  agentId: string;
  v1: number;
  v2: number;
  onClose: () => void;
}

function diffLines(oldText: string, newText: string) {
  const oldLines = oldText.split("\n");
  const newLines = newText.split("\n");
  const maxLen = Math.max(oldLines.length, newLines.length);
  const result: { type: "same" | "added" | "removed" | "changed"; oldLine?: string; newLine?: string }[] = [];

  for (let i = 0; i < maxLen; i++) {
    const a = oldLines[i];
    const b = newLines[i];
    if (a === undefined) {
      result.push({ type: "added", newLine: b });
    } else if (b === undefined) {
      result.push({ type: "removed", oldLine: a });
    } else if (a === b) {
      result.push({ type: "same", oldLine: a, newLine: b });
    } else {
      result.push({ type: "changed", oldLine: a, newLine: b });
    }
  }
  return result;
}

const FIELD_LABELS: Record<string, string> = {
  system_prompt: "System Prompt",
  model_provider: "Proveedor",
  model_name: "Modelo",
  temperature: "Temperatura",
  max_tokens: "Max Tokens",
  tools: "Tools",
};

export default function PromptCompareView({ agentId, v1, v2, onClose }: PromptCompareViewProps) {
  const { data, isLoading, error } = useCompareVersions(agentId, v1, v2);

  if (isLoading) return <LoadingSpinner />;

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
        Error al comparar versiones: {(error as Error).message}
      </div>
    );
  }

  if (!data || data.diffs.length === 0) {
    return (
      <div className="neu-flat rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">
            Comparacion: v{v1} vs v{v2}
          </h3>
          <button onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700">
            Cerrar
          </button>
        </div>
        <p className="text-sm text-gray-500">Las versiones son identicas. No hay diferencias.</p>
      </div>
    );
  }

  const promptDiff = data.diffs.find((d) => d.field === "system_prompt");
  const otherDiffs = data.diffs.filter((d) => d.field !== "system_prompt");

  return (
    <div className="neu-flat rounded-xl p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">
          Comparacion: v{data.version_a} vs v{data.version_b}
        </h3>
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-sm text-gray-600 bg-gray-100 rounded-md hover:bg-gray-200"
        >
          Cerrar
        </button>
      </div>

      {/* System prompt diff */}
      {promptDiff && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 mb-2">System Prompt</h4>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs font-medium text-gray-500 mb-1 px-2">
                Version {data.version_a}
              </div>
              <div className="bg-gray-900 rounded-lg p-3 font-mono text-xs max-h-96 overflow-y-auto">
                {diffLines(promptDiff.old_value ?? "", promptDiff.new_value ?? "").map(
                  (line, i) => (
                    <div
                      key={i}
                      className={
                        line.type === "removed"
                          ? "bg-red-900/40 text-red-300"
                          : line.type === "changed"
                          ? "bg-yellow-900/40 text-yellow-300"
                          : line.type === "added"
                          ? "opacity-30 text-gray-500"
                          : "text-green-400"
                      }
                    >
                      <span className="select-none text-gray-600 mr-2">
                        {line.type === "removed"
                          ? "-"
                          : line.type === "changed"
                          ? "~"
                          : line.type === "added"
                          ? " "
                          : " "}
                      </span>
                      {line.oldLine ?? ""}
                    </div>
                  )
                )}
              </div>
            </div>
            <div>
              <div className="text-xs font-medium text-gray-500 mb-1 px-2">
                Version {data.version_b}
              </div>
              <div className="bg-gray-900 rounded-lg p-3 font-mono text-xs max-h-96 overflow-y-auto">
                {diffLines(promptDiff.old_value ?? "", promptDiff.new_value ?? "").map(
                  (line, i) => (
                    <div
                      key={i}
                      className={
                        line.type === "added"
                          ? "bg-green-900/40 text-green-300"
                          : line.type === "changed"
                          ? "bg-yellow-900/40 text-yellow-300"
                          : line.type === "removed"
                          ? "opacity-30 text-gray-500"
                          : "text-green-400"
                      }
                    >
                      <span className="select-none text-gray-600 mr-2">
                        {line.type === "added"
                          ? "+"
                          : line.type === "changed"
                          ? "~"
                          : line.type === "removed"
                          ? " "
                          : " "}
                      </span>
                      {line.newLine ?? ""}
                    </div>
                  )
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Other field diffs */}
      {otherDiffs.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 mb-2">
            Diferencias de configuracion
          </h4>
          <div className="border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="neu-pressed-sm">
                <tr>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">Campo</th>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">
                    v{data.version_a}
                  </th>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">
                    v{data.version_b}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {otherDiffs.map((diff) => (
                  <tr key={diff.field}>
                    <td className="px-4 py-2 font-medium text-gray-700">
                      {FIELD_LABELS[diff.field] ?? diff.field}
                    </td>
                    <td className="px-4 py-2 text-red-600 bg-red-50">
                      {diff.old_value ?? "(vacio)"}
                    </td>
                    <td className="px-4 py-2 text-green-600 bg-green-50">
                      {diff.new_value ?? "(vacio)"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
