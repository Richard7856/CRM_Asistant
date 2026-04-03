/**
 * Route guard — redirects to /login if user is not authenticated.
 * Shows a loading spinner while the auth state is initializing
 * (e.g. validating a stored token on page reload).
 */

import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import LoadingSpinner from "@/components/common/LoadingSpinner";

export default function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuthStore();

  if (isLoading) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: "var(--neu-bg)" }}
      >
        <LoadingSpinner />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
