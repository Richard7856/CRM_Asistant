import { useState, useEffect, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { listInteractions, getInteractionGraph } from "@/api/interactions";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import { formatRelative } from "@/lib/formatters";
import type { InteractionGraphNode, InteractionGraphEdge } from "@/types/interaction";

const DEPT_COLORS: Record<string, string> = {
  default: "#3b82f6",
  ventas: "#10b981",
  soporte: "#f59e0b",
  ingenieria: "#8b5cf6",
  marketing: "#06b6d4",
  operaciones: "#ef4444",
  producto: "#ec4899",
  rrhh: "#f97316",
};

function getDeptColor(dept: string): string {
  const key = dept.toLowerCase();
  for (const [k, v] of Object.entries(DEPT_COLORS)) {
    if (key.includes(k)) return v;
  }
  return "#3b82f6";
}

export default function InteractionMapPage() {
  const [view, setView] = useState<"graph" | "list">("graph");

  const { data: listData, isLoading: loadingList } = useQuery({
    queryKey: ["interactions", { page: 1, size: 50 }],
    queryFn: () => listInteractions({ page: 1, size: 50 }),
  });

  const { data: graphData, isLoading: loadingGraph } = useQuery({
    queryKey: ["interactions", "graph"],
    queryFn: getInteractionGraph,
  });

  const hasGraph = graphData && graphData.nodes.length > 0;
  const activeView = hasGraph ? view : "list";

  if (loadingList && loadingGraph) return <LoadingSpinner />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">Interacciones</h1>
          <p className="text-sm text-[var(--text-muted)]">Comunicacion entre agentes</p>
        </div>
        {hasGraph && (
          <div className="flex bg-[var(--neu-dark)]/10 rounded-lg p-0.5">
            <button
              onClick={() => setView("graph")}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                activeView === "graph" ? "bg-white shadow text-[var(--text-primary)]" : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              Grafo
            </button>
            <button
              onClick={() => setView("list")}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                activeView === "list" ? "bg-white shadow text-[var(--text-primary)]" : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              Lista
            </button>
          </div>
        )}
      </div>

      {activeView === "graph" && hasGraph ? (
        <ForceGraph nodes={graphData.nodes} edges={graphData.edges} />
      ) : (
        <InteractionList items={listData?.items ?? []} />
      )}
    </div>
  );
}

/* ================== Force-directed SVG Graph ================== */

interface NodePos {
  id: string;
  name: string;
  department: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  weight: number;
}

function ForceGraph({
  nodes,
  edges,
}: {
  nodes: InteractionGraphNode[];
  edges: InteractionGraphEdge[];
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [positions, setPositions] = useState<NodePos[]>([]);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const animRef = useRef<number>(0);

  // Compute node weights
  const nodeWeightMap = new Map<string, number>();
  for (const e of edges) {
    nodeWeightMap.set(e.source, (nodeWeightMap.get(e.source) ?? 0) + e.weight);
    nodeWeightMap.set(e.target, (nodeWeightMap.get(e.target) ?? 0) + e.weight);
  }

  const maxWeight = Math.max(1, ...Array.from(nodeWeightMap.values()));
  const maxEdgeWeight = Math.max(1, ...edges.map((e) => e.weight));

  // Initialize positions
  useEffect(() => {
    const w = 700;
    const h = 450;
    const initial: NodePos[] = nodes.map((n, i) => {
      const angle = (2 * Math.PI * i) / nodes.length;
      const r = Math.min(w, h) * 0.3;
      return {
        id: n.id,
        name: n.name,
        department: n.department,
        x: w / 2 + r * Math.cos(angle) + (Math.random() - 0.5) * 40,
        y: h / 2 + r * Math.sin(angle) + (Math.random() - 0.5) * 40,
        vx: 0,
        vy: 0,
        weight: nodeWeightMap.get(n.id) ?? 1,
      };
    });
    setPositions(initial);
  }, [nodes]);

  // Simple force simulation
  const simulate = useCallback(() => {
    setPositions((prev) => {
      const next = prev.map((p) => ({ ...p }));
      const w = 700;
      const h = 450;
      const alpha = 0.3;

      // Repulsion between all nodes
      for (let i = 0; i < next.length; i++) {
        for (let j = i + 1; j < next.length; j++) {
          const ni = next[i]!;
          const nj = next[j]!;
          let dx = nj.x - ni.x;
          let dy = nj.y - ni.y;
          const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
          const force = (800 / (dist * dist)) * alpha;
          dx = (dx / dist) * force;
          dy = (dy / dist) * force;
          ni.vx -= dx;
          ni.vy -= dy;
          nj.vx += dx;
          nj.vy += dy;
        }
      }

      // Attraction along edges
      const posMap = new Map(next.map((n) => [n.id, n]));
      for (const e of edges) {
        const s = posMap.get(e.source);
        const t = posMap.get(e.target);
        if (!s || !t) continue;
        const dx = t.x - s.x;
        const dy = t.y - s.y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const force = ((dist - 120) * 0.01) * alpha;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        s.vx += fx;
        s.vy += fy;
        t.vx -= fx;
        t.vy -= fy;
      }

      // Center gravity
      for (const n of next) {
        n.vx += (w / 2 - n.x) * 0.005;
        n.vy += (h / 2 - n.y) * 0.005;
      }

      // Apply velocities with damping
      for (const n of next) {
        n.vx *= 0.6;
        n.vy *= 0.6;
        n.x += n.vx;
        n.y += n.vy;
        n.x = Math.max(40, Math.min(w - 40, n.x));
        n.y = Math.max(40, Math.min(h - 40, n.y));
      }

      return next;
    });
  }, [edges]);

  useEffect(() => {
    let frame = 0;
    const maxFrames = 150;
    const tick = () => {
      if (frame < maxFrames) {
        simulate();
        frame++;
        animRef.current = requestAnimationFrame(tick);
      }
    };
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, [simulate, positions.length]);

  const posMap = new Map(positions.map((p) => [p.id, p]));
  const activeNode = selectedNode ?? hoveredNode;

  // Connected edges for active node
  const connectedEdges = activeNode
    ? edges.filter((e) => e.source === activeNode || e.target === activeNode)
    : [];
  const connectedNodeIds = new Set(connectedEdges.flatMap((e) => [e.source, e.target]));

  return (
    <div className="neu-flat rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-[var(--text-secondary)]">Mapa de Interacciones</h3>
        {activeNode && (
          <button
            onClick={() => { setSelectedNode(null); setHoveredNode(null); }}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
          >
            Limpiar seleccion
          </button>
        )}
      </div>

      <svg
        ref={svgRef}
        viewBox="0 0 700 450"
        className="w-full border rounded-lg bg-[var(--neu-bg)]"
        style={{ maxHeight: "500px" }}
      >
        {/* Edges */}
        {edges.map((e, i) => {
          const s = posMap.get(e.source);
          const t = posMap.get(e.target);
          if (!s || !t) return null;
          const isActive = activeNode && (e.source === activeNode || e.target === activeNode);
          const opacity = activeNode ? (isActive ? 0.7 : 0.08) : 0.25;
          const strokeWidth = 1 + (e.weight / maxEdgeWeight) * 4;
          return (
            <line
              key={i}
              x1={s.x}
              y1={s.y}
              x2={t.x}
              y2={t.y}
              stroke="#94a3b8"
              strokeWidth={strokeWidth}
              opacity={opacity}
              strokeLinecap="round"
            />
          );
        })}

        {/* Nodes */}
        {positions.map((node) => {
          const r = 10 + (node.weight / maxWeight) * 18;
          const color = getDeptColor(node.department);
          const isActive = node.id === activeNode;
          const isConnected = connectedNodeIds.has(node.id);
          const opacity = activeNode ? (isActive || isConnected ? 1 : 0.2) : 1;

          return (
            <g
              key={node.id}
              transform={`translate(${node.x},${node.y})`}
              style={{ cursor: "pointer", opacity }}
              onMouseEnter={() => !selectedNode && setHoveredNode(node.id)}
              onMouseLeave={() => !selectedNode && setHoveredNode(null)}
              onClick={() => setSelectedNode(selectedNode === node.id ? null : node.id)}
            >
              <circle
                r={r}
                fill={color}
                stroke={isActive ? "#1e293b" : "#fff"}
                strokeWidth={isActive ? 3 : 2}
                opacity={0.85}
              />
              <text
                y={r + 14}
                textAnchor="middle"
                fill="#374151"
                fontSize="10"
                fontWeight="500"
              >
                {node.name.length > 14 ? node.name.slice(0, 14) + "..." : node.name}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Details panel */}
      {activeNode && (
        <div className="mt-3 p-3 bg-[var(--neu-bg)] rounded-lg border text-sm">
          <p className="font-semibold text-[var(--text-primary)]">
            {positions.find((p) => p.id === activeNode)?.name ?? "Agente"}
          </p>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            Departamento: {positions.find((p) => p.id === activeNode)?.department ?? "--"}
          </p>
          <div className="mt-2 space-y-1">
            {connectedEdges.map((e, i) => {
              const otherNode = e.source === activeNode
                ? positions.find((p) => p.id === e.target)
                : positions.find((p) => p.id === e.source);
              return (
                <div key={i} className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
                  <span>
                    {e.source === activeNode ? "→" : "←"} {otherNode?.name ?? "??"} ({e.weight} interacciones)
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="mt-3 flex flex-wrap gap-3">
        {Array.from(new Set(nodes.map((n) => n.department))).map((dept) => (
          <div key={dept} className="flex items-center gap-1.5">
            <span
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: getDeptColor(dept) }}
            />
            <span className="text-xs text-[var(--text-secondary)]">{dept}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ================== Interaction List ================== */

function InteractionList({ items }: { items: { id: string; from_agent_name?: string; to_agent_name?: string; payload_summary?: string | null; success: boolean; occurred_at: string }[] }) {
  if (items.length === 0) {
    return (
      <div className="neu-flat rounded-xl p-8 text-center">
        <p className="text-[var(--text-muted)] text-sm">No hay interacciones registradas.</p>
      </div>
    );
  }

  return (
    <div className="neu-flat rounded-xl divide-y">
      {items.map((interaction) => (
        <div key={interaction.id} className="px-4 py-3 flex items-center gap-4 hover:bg-[var(--neu-dark)]/20 transition-colors">
          <div className="flex-1 min-w-0">
            <p className="text-sm">
              <span className="font-medium text-[var(--text-primary)]">{interaction.from_agent_name ?? "Agente"}</span>
              <span className="text-[var(--text-muted)] mx-2">&rarr;</span>
              <span className="font-medium text-[var(--text-primary)]">{interaction.to_agent_name ?? "Agente"}</span>
            </p>
            {interaction.payload_summary && (
              <p className="text-xs text-[var(--text-muted)] mt-0.5 truncate">{interaction.payload_summary}</p>
            )}
          </div>
          <span
            className={`text-xs px-2.5 py-1 rounded-full font-medium ${
              interaction.success
                ? "bg-green-50 text-green-700 ring-1 ring-green-200"
                : "bg-red-50 text-red-700 ring-1 ring-red-200"
            }`}
          >
            {interaction.success ? "OK" : "Error"}
          </span>
          <span className="text-xs text-[var(--text-muted)] whitespace-nowrap">
            {formatRelative(interaction.occurred_at)}
          </span>
        </div>
      ))}
    </div>
  );
}
