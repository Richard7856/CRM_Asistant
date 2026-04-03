/**
 * Login / Register page — neumorphic design with tab toggle.
 * Handles both authentication flows in a single page to keep
 * the demo flow smooth (no extra navigation).
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, LogIn, UserPlus, Eye, EyeOff, AlertCircle } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";

type Mode = "login" | "register";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, register } = useAuthStore();

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, fullName, orgName);
      }
      navigate("/", { replace: true });
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(
        axiosErr.response?.data?.detail || "Error de autenticación. Intenta de nuevo.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: "var(--neu-bg)" }}
    >
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex flex-col items-center mb-10">
          <div className="neu-flat w-16 h-16 rounded-2xl flex items-center justify-center mb-4">
            <Bot className="w-8 h-8 text-indigo-500" />
          </div>
          <h1 className="text-xl font-bold text-[var(--text-primary)]">CRM Agents</h1>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Gestiona tu equipo de agentes IA
          </p>
        </div>

        {/* Tab toggle */}
        <div className="neu-pressed-sm rounded-xl p-1 flex mb-8">
          <button
            type="button"
            onClick={() => { setMode("login"); setError(null); }}
            className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 flex items-center justify-center gap-2 ${
              mode === "login"
                ? "neu-sm text-[var(--text-primary)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            }`}
          >
            <LogIn className="w-4 h-4" />
            Iniciar Sesión
          </button>
          <button
            type="button"
            onClick={() => { setMode("register"); setError(null); }}
            className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 flex items-center justify-center gap-2 ${
              mode === "register"
                ? "neu-sm text-[var(--text-primary)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            }`}
          >
            <UserPlus className="w-4 h-4" />
            Registrarse
          </button>
        </div>

        {/* Form card */}
        <div className="neu-flat rounded-2xl p-8">
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Error message */}
            {error && (
              <div className="neu-pressed-sm rounded-xl p-3 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            {/* Register-only fields */}
            {mode === "register" && (
              <>
                <div>
                  <label className="block text-xs font-medium text-[var(--text-secondary)] mb-2">
                    Nombre completo
                  </label>
                  <div className="neu-pressed-sm rounded-xl px-4 py-3">
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Tu nombre"
                      required
                      className="bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none w-full"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-[var(--text-secondary)] mb-2">
                    Organización
                  </label>
                  <div className="neu-pressed-sm rounded-xl px-4 py-3">
                    <input
                      type="text"
                      value={orgName}
                      onChange={(e) => setOrgName(e.target.value)}
                      placeholder="Nombre de tu empresa"
                      required
                      className="bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none w-full"
                    />
                  </div>
                </div>
              </>
            )}

            {/* Email */}
            <div>
              <label className="block text-xs font-medium text-[var(--text-secondary)] mb-2">
                Correo electrónico
              </label>
              <div className="neu-pressed-sm rounded-xl px-4 py-3">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="tu@empresa.com"
                  required
                  className="bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none w-full"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-medium text-[var(--text-secondary)] mb-2">
                Contraseña
              </label>
              <div className="neu-pressed-sm rounded-xl px-4 py-3 flex items-center gap-2">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === "register" ? "Mínimo 8 caracteres" : "••••••••"}
                  required
                  minLength={mode === "register" ? 8 : undefined}
                  className="bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none w-full"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3.5 rounded-xl text-sm font-semibold text-white transition-all duration-200 disabled:opacity-50"
              style={{
                background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                boxShadow:
                  "6px 6px 12px 0 var(--neu-dark), -6px -6px 12px 0 var(--neu-light)",
              }}
            >
              {loading
                ? "Procesando..."
                : mode === "login"
                  ? "Iniciar Sesión"
                  : "Crear Cuenta"}
            </button>
          </form>
        </div>

        {/* Demo hint */}
        <p className="text-center text-xs text-[var(--text-muted)] mt-6">
          Demo: richard@crmagents.io / Demo2026!
        </p>
      </div>
    </div>
  );
}
