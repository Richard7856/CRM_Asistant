/**
 * App header — search bar, notifications, and user profile badge.
 * Pulls real user data from authStore and shows a logout button.
 */

import { useState } from "react";
import { Search, Bell, LogOut, ChevronDown } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";

/** Get uppercase initials from a name (e.g. "Richard Figueroa" → "RF") */
function getInitials(name: string): string {
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

/** Capitalize first letter */
function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function Header() {
  const { user, logout } = useAuthStore();
  const [showMenu, setShowMenu] = useState(false);

  return (
    <header className="h-16 flex items-center justify-between px-6">
      {/* Search — neumorphic inset field */}
      <div className="neu-pressed-sm flex items-center gap-2 px-4 py-2.5 w-80">
        <Search className="w-4 h-4 text-[var(--text-muted)]" />
        <input
          type="text"
          placeholder="Buscar agentes, tareas..."
          className="bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none w-full"
        />
      </div>

      {/* Right section */}
      <div className="flex items-center gap-4">
        <button className="neu-sm p-2.5 hover:shadow-none transition-shadow duration-200 active:shadow-[inset_3px_3px_6px_0_var(--neu-dark),inset_-3px_-3px_6px_0_var(--neu-light)]">
          <Bell className="w-4 h-4 text-[var(--text-secondary)]" />
        </button>

        {/* User badge with dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="neu-sm flex items-center gap-2.5 px-3 py-2 transition-shadow duration-200 hover:shadow-none"
          >
            <div className="w-7 h-7 rounded-full bg-indigo-500/15 flex items-center justify-center">
              <span className="text-xs font-bold text-indigo-500">
                {user ? getInitials(user.full_name) : "??"}
              </span>
            </div>
            <div className="text-left hidden sm:block">
              <p className="text-xs font-medium text-[var(--text-primary)] leading-tight">
                {user?.full_name ?? "Cargando..."}
              </p>
              <p className="text-[10px] text-[var(--text-muted)] leading-tight">
                {user ? capitalize(user.role) : ""}
                {user?.organization_name ? ` · ${user.organization_name}` : ""}
              </p>
            </div>
            <ChevronDown className="w-3 h-3 text-[var(--text-muted)]" />
          </button>

          {/* Dropdown menu */}
          {showMenu && (
            <>
              {/* Backdrop to close menu */}
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowMenu(false)}
              />
              <div className="absolute right-0 top-full mt-2 z-50 neu-flat rounded-xl p-1.5 min-w-[180px]">
                <div className="px-3 py-2 border-b border-[var(--neu-dark)]/10 mb-1">
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    {user?.email}
                  </p>
                  <p className="text-[10px] text-[var(--text-muted)]">
                    {user?.organization_name}
                  </p>
                </div>
                <button
                  onClick={() => {
                    setShowMenu(false);
                    logout();
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-red-400 hover:bg-red-500/5 rounded-lg transition-colors"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  Cerrar sesión
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
