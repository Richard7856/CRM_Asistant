import { NavLink } from "react-router-dom";
import { useUIStore } from "@/stores/uiStore";
import { ROUTES } from "@/lib/routes";
import {
  LayoutDashboard,
  Crown,
  Bot,
  Network,
  Building2,
  ListChecks,
  Activity,
  BarChart3,
  ArrowRightLeft,
  Lightbulb,
  Wand2,
  Plug,
  BookOpen,
  Key,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

const navItems = [
  { path: ROUTES.DASHBOARD, label: "Dashboard", Icon: LayoutDashboard },
  { path: ROUTES.CEO, label: "CEO View", Icon: Crown },
  { path: ROUTES.AGENTS, label: "Agentes", Icon: Bot },
  { path: ROUTES.ORG_CHART, label: "Organigrama", Icon: Network },
  { path: ROUTES.DEPARTMENTS, label: "Departamentos", Icon: Building2 },
  { path: ROUTES.TASKS, label: "Tareas", Icon: ListChecks },
  { path: ROUTES.ACTIVITIES, label: "Actividad", Icon: Activity },
  { path: ROUTES.METRICS, label: "Metricas", Icon: BarChart3 },
  { path: ROUTES.INTERACTIONS, label: "Interacciones", Icon: ArrowRightLeft },
  { path: ROUTES.IMPROVEMENTS, label: "Mejoras", Icon: Lightbulb },
  { path: ROUTES.PROMPTS, label: "Prompts", Icon: Wand2 },
  { path: ROUTES.INTEGRATIONS, label: "Integraciones", Icon: Plug },
  { path: ROUTES.KNOWLEDGE, label: "Conocimiento", Icon: BookOpen },
  { path: ROUTES.CREDENTIALS, label: "Credenciales", Icon: Key },
];

export default function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useUIStore();

  return (
    <aside
      className={`fixed top-0 left-0 h-screen neu-dark text-white/90 transition-all duration-300 z-30 flex flex-col ${
        sidebarCollapsed ? "w-[68px]" : "w-60"
      }`}
    >
      {/* Brand */}
      <div className="flex items-center justify-between px-4 py-5">
        {!sidebarCollapsed && (
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-indigo-500/20 flex items-center justify-center">
              <Bot className="w-4.5 h-4.5 text-indigo-400" />
            </div>
            <span className="text-sm font-semibold tracking-tight text-white/90">
              CRM Agents
            </span>
          </div>
        )}
        <button
          onClick={toggleSidebar}
          className="p-1.5 rounded-lg text-white/40 hover:text-white/80 transition-colors"
        >
          {sidebarCollapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <ChevronLeft className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200 ${
                isActive
                  ? "neu-dark-pressed text-indigo-400"
                  : "text-white/50 hover:text-white/80 hover:bg-white/[0.04]"
              }`
            }
          >
            <item.Icon
              className="w-[18px] h-[18px] flex-shrink-0"
              strokeWidth={1.8}
            />
            {!sidebarCollapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4">
        {!sidebarCollapsed && (
          <span className="text-[11px] text-white/20 font-mono">v0.1.0</span>
        )}
      </div>
    </aside>
  );
}
