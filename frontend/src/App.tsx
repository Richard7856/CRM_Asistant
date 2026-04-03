import { lazy, Suspense, useEffect } from "react";
import { Routes, Route } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppShell from "./components/layout/AppShell";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import ErrorBoundary from "@/components/common/ErrorBoundary";

// Lazy-loaded route pages — each becomes its own chunk
const LoginPage = lazy(() => import("./features/auth/LoginPage"));
const DashboardPage = lazy(() => import("./features/dashboard/DashboardPage"));
const CeoDashboardPage = lazy(() => import("./features/dashboard/CeoDashboardPage"));
const AgentListPage = lazy(() => import("./features/agents/AgentListPage"));
const AgentDetailPage = lazy(() => import("./features/agents/AgentDetailPage"));
const CreateAgentPage = lazy(() => import("./features/agents/CreateAgentPage"));
const RegisterExternalAgentPage = lazy(() => import("./features/agents/RegisterExternalAgentPage"));
const OrgChartPage = lazy(() => import("./features/org-chart/OrgChartPage"));
const DepartmentListPage = lazy(() => import("./features/departments/DepartmentListPage"));
const DepartmentDetailPage = lazy(() => import("./features/departments/DepartmentDetailPage"));
const TaskListPage = lazy(() => import("./features/tasks/TaskListPage"));
const CreateTaskPage = lazy(() => import("./features/tasks/CreateTaskPage"));
const ActivityLogPage = lazy(() => import("./features/activities/ActivityLogPage"));
const MetricsDashboardPage = lazy(() => import("./features/metrics/MetricsDashboardPage"));
const InteractionMapPage = lazy(() => import("./features/interactions/InteractionMapPage"));
const ImprovementsPage = lazy(() => import("./features/improvements/ImprovementsPage"));
const PromptEngineeringPage = lazy(() => import("./features/prompts/PromptEngineeringPage"));
const IntegrationsPage = lazy(() => import("./features/integrations/IntegrationsPage"));
const KnowledgePage = lazy(() => import("./features/knowledge/KnowledgePage"));

export default function App() {
  const initialize = useAuthStore((s) => s.initialize);

  // Hydrate auth state from localStorage on app boot
  useEffect(() => {
    initialize();
  }, [initialize]);

  return (
    <Suspense fallback={<LoadingSpinner />}>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected routes — redirect to /login if no session */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<ErrorBoundary section="Dashboard"><DashboardPage /></ErrorBoundary>} />
            <Route path="agents" element={<ErrorBoundary section="Agentes"><AgentListPage /></ErrorBoundary>} />
            <Route path="agents/new" element={<ErrorBoundary section="Crear Agente"><CreateAgentPage /></ErrorBoundary>} />
            <Route path="agents/register" element={<ErrorBoundary section="Registrar Agente"><RegisterExternalAgentPage /></ErrorBoundary>} />
            <Route path="agents/:id" element={<ErrorBoundary section="Detalle de Agente"><AgentDetailPage /></ErrorBoundary>} />
            <Route path="org-chart" element={<ErrorBoundary section="Organigrama"><OrgChartPage /></ErrorBoundary>} />
            <Route path="departments" element={<ErrorBoundary section="Departamentos"><DepartmentListPage /></ErrorBoundary>} />
            <Route path="departments/:id" element={<ErrorBoundary section="Detalle de Departamento"><DepartmentDetailPage /></ErrorBoundary>} />
            <Route path="tasks" element={<ErrorBoundary section="Tareas"><TaskListPage /></ErrorBoundary>} />
            <Route path="tasks/new" element={<ErrorBoundary section="Crear Tarea"><CreateTaskPage /></ErrorBoundary>} />
            <Route path="ceo" element={<ErrorBoundary section="CEO Dashboard"><CeoDashboardPage /></ErrorBoundary>} />
            <Route path="activities" element={<ErrorBoundary section="Actividades"><ActivityLogPage /></ErrorBoundary>} />
            <Route path="metrics" element={<ErrorBoundary section="Metricas"><MetricsDashboardPage /></ErrorBoundary>} />
            <Route path="interactions" element={<ErrorBoundary section="Interacciones"><InteractionMapPage /></ErrorBoundary>} />
            <Route path="improvements" element={<ErrorBoundary section="Mejoras"><ImprovementsPage /></ErrorBoundary>} />
            <Route path="prompts" element={<ErrorBoundary section="Prompts"><PromptEngineeringPage /></ErrorBoundary>} />
            <Route path="integrations" element={<ErrorBoundary section="Integraciones"><IntegrationsPage /></ErrorBoundary>} />
            <Route path="knowledge" element={<ErrorBoundary section="Conocimiento"><KnowledgePage /></ErrorBoundary>} />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  );
}
