/**
 * KnowledgePage — manage the organization's RAG knowledge base.
 *
 * Two tabs:
 *   "Documentos" — table of ingested docs with chunk count, scope, delete
 *   "Agregar"    — paste text, title, optional dept, auto-chunk on submit
 *
 * Chunking strategy: split on double newline (\n\n) in the frontend before posting.
 * Each paragraph becomes one chunk. Simple and effective for structured text.
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { BookOpen, Plus, Trash2, Search, FileText, Globe, Building2 } from "lucide-react";
import {
  listDocuments,
  ingestDocument,
  deleteDocument,
  searchKnowledge,
  type KnowledgeDocument,
  type KnowledgeSearchResult,
} from "@/api/knowledge";
import { listDepartments } from "@/api/departments";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import { formatRelative } from "@/lib/formatters";

type Tab = "documents" | "add" | "search";

const ingestSchema = z.object({
  title: z.string().min(1, "El título es requerido").max(300),
  description: z.string().optional(),
  department_id: z.string().optional(),
  content: z.string().min(10, "El contenido debe tener al menos 10 caracteres"),
});

type IngestForm = z.infer<typeof ingestSchema>;

export default function KnowledgePage() {
  const [activeTab, setActiveTab] = useState<Tab>("documents");
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: docs, isLoading } = useQuery({
    queryKey: ["knowledge"],
    queryFn: () => listDocuments({ page: 1, size: 50 }),
  });

  const { data: deptsData } = useQuery({
    queryKey: ["departments", { page: 1, size: 50 }],
    queryFn: () => listDepartments({ page: 1, size: 50 }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge"] });
      setDeleteConfirm(null);
    },
  });

  const departments = deptsData?.items ?? [];

  const tab = (id: Tab, label: string, Icon: React.ElementType) => (
    <button
      onClick={() => setActiveTab(id)}
      className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all ${
        activeTab === id
          ? "neu-pressed text-indigo-500"
          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      }`}
    >
      <Icon className="w-4 h-4" />
      {label}
    </button>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">Base de Conocimiento</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            Documentos que los agentes pueden consultar al ejecutar tareas (RAG)
          </p>
        </div>
        <div className="flex items-center gap-1 neu-pressed rounded-xl p-1">
          {tab("documents", "Documentos", FileText)}
          {tab("add", "Agregar", Plus)}
          {tab("search", "Buscar", Search)}
        </div>
      </div>

      {/* ===== DOCUMENTS TAB ===== */}
      {activeTab === "documents" && (
        <div className="neu-flat rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--neu-dark)] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              Documentos ingresados
              {docs?.total ? (
                <span className="ml-2 text-xs font-normal text-[var(--text-secondary)]">
                  ({docs.total} total)
                </span>
              ) : null}
            </h2>
          </div>

          {isLoading ? (
            <div className="p-8 flex justify-center"><LoadingSpinner /></div>
          ) : !docs?.items?.length ? (
            <div className="p-12 text-center">
              <div className="neu-pressed w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
                <BookOpen className="w-8 h-8 text-[var(--text-secondary)]" />
              </div>
              <p className="text-[var(--text-secondary)] font-medium">Sin documentos aún</p>
              <p className="text-sm text-[var(--text-secondary)] mt-1 opacity-70">
                Agrega documentos para que los agentes puedan usarlos como contexto
              </p>
              <button
                onClick={() => setActiveTab("add")}
                className="mt-4 px-4 py-2 neu-sm text-sm font-medium text-indigo-500 hover:text-indigo-600 transition-colors"
              >
                Agregar primer documento
              </button>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="neu-pressed-sm border-b border-[var(--neu-dark)]">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">Título</th>
                  <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">Alcance</th>
                  <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">Fragmentos</th>
                  <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">Tipo</th>
                  <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">Creado</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--neu-dark)]">
                {docs.items.map((doc) => (
                  <DocumentRow
                    key={doc.id}
                    doc={doc}
                    departments={departments}
                    onDelete={() => setDeleteConfirm(doc.id)}
                    isDeleting={deleteMutation.isPending && deleteConfirm === doc.id}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ===== ADD TAB ===== */}
      {activeTab === "add" && (
        <AddDocumentForm
          departments={departments}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["knowledge"] });
            setActiveTab("documents");
          }}
        />
      )}

      {/* ===== SEARCH TAB ===== */}
      {activeTab === "search" && (
        <SearchKnowledge departments={departments} />
      )}

      {/* ===== DELETE CONFIRM MODAL ===== */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="neu-flat rounded-2xl p-6 max-w-sm w-full mx-4 space-y-4">
            <h3 className="text-base font-semibold text-[var(--text-primary)]">Eliminar documento?</h3>
            <p className="text-sm text-[var(--text-secondary)]">
              Se eliminarán también todos sus fragmentos. Los agentes ya no podrán usar este conocimiento.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-4 py-2 neu-sm text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteConfirm)}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {deleteMutation.isPending ? "Eliminando..." : "Eliminar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ==================== Sub-components ==================== */

function DocumentRow({
  doc,
  departments,
  onDelete,
  isDeleting,
}: {
  doc: KnowledgeDocument;
  departments: Array<{ id: string; name: string }>;
  onDelete: () => void;
  isDeleting: boolean;
}) {
  const dept = departments.find((d) => d.id === doc.department_id);

  return (
    <tr className="hover:bg-[var(--neu-dark)]/20 transition-colors">
      <td className="px-4 py-3">
        <p className="font-medium text-[var(--text-primary)]">{doc.title}</p>
        {doc.description && (
          <p className="text-xs text-[var(--text-secondary)] mt-0.5 truncate max-w-xs">{doc.description}</p>
        )}
      </td>
      <td className="px-4 py-3">
        {doc.department_id ? (
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 neu-pressed-sm px-2 py-1 rounded-lg">
            <Building2 className="w-3 h-3" />
            {dept?.name ?? "Departamento"}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-500 neu-pressed-sm px-2 py-1 rounded-lg">
            <Globe className="w-3 h-3" />
            Toda la org
          </span>
        )}
      </td>
      <td className="px-4 py-3">
        <span className="text-sm font-medium text-[var(--text-primary)]">{doc.chunk_count ?? "—"}</span>
        <span className="text-xs text-[var(--text-secondary)] ml-1">fragmentos</span>
      </td>
      <td className="px-4 py-3">
        <span className="text-xs text-[var(--text-secondary)] uppercase tracking-wide">
          {doc.file_type ?? "texto"}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-[var(--text-secondary)] opacity-70">
        {formatRelative(doc.created_at)}
      </td>
      <td className="px-4 py-3">
        <button
          onClick={onDelete}
          disabled={isDeleting}
          className="p-1.5 rounded-lg hover:bg-red-500/20 text-[var(--text-secondary)] hover:text-red-500 transition-colors disabled:opacity-40"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </td>
    </tr>
  );
}

function AddDocumentForm({
  departments,
  onSuccess,
}: {
  departments: Array<{ id: string; name: string }>;
  onSuccess: () => void;
}) {
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
    reset,
  } = useForm<IngestForm>({ resolver: zodResolver(ingestSchema) });

  const content = watch("content") ?? "";

  // Preview chunk count — split on double newline
  const chunks = content.split(/\n\n+/).filter((c) => c.trim().length > 0);

  const mutation = useMutation({
    mutationFn: ingestDocument,
    onSuccess: () => {
      reset();
      onSuccess();
    },
  });

  const onSubmit = (data: IngestForm) => {
    const chunkInputs = chunks.map((text, i) => ({
      content: text.trim(),
      chunk_index: i,
    }));

    mutation.mutate({
      document: {
        title: data.title,
        description: data.description || undefined,
        department_id: data.department_id || undefined,
        file_type: "text",
      },
      chunks: chunkInputs,
    });
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="neu-flat rounded-xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">Nuevo documento</h2>

        {/* Title */}
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
            Título <span className="text-red-400">*</span>
          </label>
          <input
            {...register("title")}
            placeholder="Ej: Manual de ventas Q1, Precios 2026, FAQ soporte..."
            className="w-full neu-pressed rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]/50 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          />
          {errors.title && <p className="text-xs text-red-400 mt-1">{errors.title.message}</p>}
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
            Descripción (opcional)
          </label>
          <input
            {...register("description")}
            placeholder="Breve descripción del contenido..."
            className="w-full neu-pressed rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]/50 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          />
        </div>

        {/* Department scope */}
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
            Alcance
          </label>
          <select
            {...register("department_id")}
            className="w-full neu-pressed rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          >
            <option value="">Toda la organización (todos los agentes)</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                Solo {d.name}
              </option>
            ))}
          </select>
          <p className="text-xs text-[var(--text-secondary)] mt-1 opacity-70">
            "Toda la organización" = accesible por todos los agentes. Por departamento = solo agentes de ese dept.
          </p>
        </div>

        {/* Content */}
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
            Contenido <span className="text-red-400">*</span>
          </label>
          <textarea
            {...register("content")}
            rows={12}
            placeholder={`Pega aquí el contenido del documento.\n\nCada párrafo separado por una línea en blanco se convierte en un fragmento independiente que los agentes pueden recuperar de forma precisa.\n\nEjemplo:\n\nNuestro producto principal es el CRM Agents, una plataforma para gestionar agentes de IA como un equipo humano.\n\nLos precios son: Plan Básico $99/mes, Plan Pro $299/mes, Plan Enterprise a consultar.`}
            className="w-full neu-pressed rounded-lg px-3 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]/40 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 font-mono leading-relaxed resize-y"
          />
          {errors.content && <p className="text-xs text-red-400 mt-1">{errors.content.message}</p>}

          {/* Chunk preview */}
          {chunks.length > 0 && (
            <div className="mt-2 flex items-center gap-2 text-xs text-[var(--text-secondary)]">
              <span className="neu-pressed-sm px-2 py-0.5 rounded-md font-medium text-indigo-500">
                {chunks.length} fragmento{chunks.length !== 1 ? "s" : ""}
              </span>
              <span className="opacity-70">se indexarán para búsqueda</span>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={() => reset()}
            className="px-4 py-2 neu-sm text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            Limpiar
          </button>
          <button
            type="submit"
            disabled={mutation.isPending || chunks.length === 0}
            className="px-5 py-2 bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
          >
            {mutation.isPending ? (
              <><span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" /> Indexando...</>
            ) : (
              <><Plus className="w-4 h-4" /> Agregar al Knowledge Base</>
            )}
          </button>
        </div>

        {mutation.isError && (
          <p className="text-sm text-red-400 text-center">
            Error al indexar. Verifica que el servidor esté corriendo.
          </p>
        )}
      </div>
    </form>
  );
}

function SearchKnowledge({
  departments,
}: {
  departments: Array<{ id: string; name: string }>;
}) {
  const [query, setQuery] = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [results, setResults] = useState<KnowledgeSearchResult[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setIsSearching(true);
    try {
      const res = await searchKnowledge({
        q: query,
        department_id: deptFilter || undefined,
        limit: 10,
      });
      setResults(res);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="neu-flat rounded-xl p-4 space-y-3">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">Probar búsqueda</h2>
        <p className="text-xs text-[var(--text-secondary)] opacity-70">
          Simula lo que un agente buscaría cuando ejecuta una tarea
        </p>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Ej: precios producto, política de soporte, proceso de ventas..."
            className="flex-1 neu-pressed rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]/50 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          />
          <select
            value={deptFilter}
            onChange={(e) => setDeptFilter(e.target.value)}
            className="neu-pressed rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          >
            <option value="">Todos</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
          <button
            onClick={handleSearch}
            disabled={isSearching || !query.trim()}
            className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
          >
            {isSearching ? (
              <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            Buscar
          </button>
        </div>
      </div>

      {results !== null && (
        <div className="space-y-3">
          {results.length === 0 ? (
            <div className="neu-flat rounded-xl p-8 text-center">
              <p className="text-[var(--text-secondary)]">Sin resultados para "{query}"</p>
              <p className="text-xs text-[var(--text-secondary)] mt-1 opacity-70">
                Intenta con términos más simples o agrega documentos relevantes
              </p>
            </div>
          ) : (
            results.map((r, i) => (
              <div key={r.chunk.id} className="neu-flat rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-indigo-500 neu-pressed-sm px-2 py-0.5 rounded-md">
                      #{i + 1}
                    </span>
                    <span className="text-sm font-medium text-[var(--text-primary)]">{r.document_title}</span>
                    {r.department_id ? (
                      <span className="text-xs text-blue-500 neu-pressed-sm px-2 py-0.5 rounded-md">
                        {departments.find((d) => d.id === r.department_id)?.name ?? "Dept"}
                      </span>
                    ) : (
                      <span className="text-xs text-indigo-400 neu-pressed-sm px-2 py-0.5 rounded-md">Org</span>
                    )}
                  </div>
                  <span className="text-xs text-[var(--text-secondary)] opacity-60">
                    relevancia: {(r.rank * 100).toFixed(1)}%
                  </span>
                </div>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed bg-[var(--neu-dark)]/10 rounded-lg p-3 font-mono text-xs">
                  {r.chunk.content}
                </p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
