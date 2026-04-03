import { useCallback } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Header from "./Header";
import ToastContainer from "@/components/common/ToastContainer";
import { useUIStore } from "@/stores/uiStore";
import { useToastStore } from "@/stores/toastStore";
import { useEventStream } from "@/hooks/useEventStream";

export default function AppShell() {
  const { sidebarCollapsed } = useUIStore();
  const addToast = useToastStore((s) => s.addToast);

  const handleSSEEvent = useCallback(
    (event: { type: string; data: Record<string, unknown> }) => {
      switch (event.type) {
        case "task.completed":
          addToast({
            type: "success",
            title: "Tarea completada",
            message: `${event.data.agent_name}: ${event.data.title}`,
          });
          break;
        case "task.failed":
          addToast({
            type: "error",
            title: "Tarea fallida",
            message: `${event.data.agent_name}: ${event.data.title}`,
          });
          break;
        case "task.started":
          addToast({
            type: "info",
            title: "Agente trabajando",
            message: `${event.data.agent_name} ejecutando: ${event.data.title}`,
          });
          break;
      }
    },
    [addToast],
  );
  useEventStream(handleSSEEvent);

  return (
    <div
      className="min-h-screen"
      style={{ background: "var(--neu-bg)" }}
    >
      <Sidebar />
      <div
        className={`transition-all duration-300 ${
          sidebarCollapsed ? "ml-[68px]" : "ml-60"
        }`}
      >
        <Header />
        <main className="px-6 pb-8 animate-fade-in">
          <Outlet />
        </main>
      </div>
      <ToastContainer />
    </div>
  );
}
