/**
 * UI state — sidebar collapse + theme preference.
 *
 * Theme persists to localStorage so the user's choice survives page reloads.
 * On init, we also apply the .dark class to <html> immediately to prevent
 * a flash of light mode (FOLT).
 */
import { create } from "zustand";

type Theme = "light" | "dark";

const THEME_KEY = "crm-agents-theme";

/** Read saved theme or fall back to system preference */
function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "dark" || saved === "light") return saved;
  // Respect OS-level preference if no explicit choice
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Apply or remove .dark class on <html> element */
function applyThemeClass(theme: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", theme === "dark");
}

// Apply immediately on module load — prevents flash of wrong theme
const initialTheme = getInitialTheme();
applyThemeClass(initialTheme);

interface UIState {
  sidebarCollapsed: boolean;
  theme: Theme;
  toggleSidebar: () => void;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

export const useUIStore = create<UIState>((set, get) => ({
  sidebarCollapsed: false,
  theme: initialTheme,

  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  toggleTheme: () => {
    const next = get().theme === "light" ? "dark" : "light";
    localStorage.setItem(THEME_KEY, next);
    applyThemeClass(next);
    set({ theme: next });
  },

  setTheme: (theme: Theme) => {
    localStorage.setItem(THEME_KEY, theme);
    applyThemeClass(theme);
    set({ theme });
  },
}));
