/**
 * Auth state — manages JWT tokens, user profile, and session lifecycle.
 * Tokens are persisted in localStorage so the session survives page reloads.
 * The store exposes login/register/logout actions that call the API and
 * update state atomically.
 */

import { create } from "zustand";
import {
  type TokenResponse,
  type UserProfile,
  loginApi,
  registerApi,
  refreshApi,
  getMeApi,
} from "@/api/auth";

const TOKEN_KEY = "crm_access_token";
const REFRESH_KEY = "crm_refresh_token";

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: UserProfile | null;
  isLoading: boolean;
  isAuthenticated: boolean;

  /** Hydrate session from localStorage on app boot */
  initialize: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string, orgName: string) => Promise<void>;
  logout: () => void;
  /** Silent token refresh — called by the axios interceptor on 401 */
  refresh: () => Promise<string | null>;
}

function persistTokens(tokens: TokenResponse) {
  localStorage.setItem(TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  refreshToken: null,
  user: null,
  isLoading: true,
  isAuthenticated: false,

  initialize: async () => {
    const token = localStorage.getItem(TOKEN_KEY);
    const refreshToken = localStorage.getItem(REFRESH_KEY);

    if (!token) {
      set({ isLoading: false });
      return;
    }

    set({ token, refreshToken });

    try {
      const user = await getMeApi();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch {
      // Token expired — try refresh
      if (refreshToken) {
        try {
          const tokens = await refreshApi(refreshToken);
          persistTokens(tokens);
          set({ token: tokens.access_token, refreshToken: tokens.refresh_token });
          const user = await getMeApi();
          set({ user, isAuthenticated: true, isLoading: false });
        } catch {
          clearTokens();
          set({ token: null, refreshToken: null, user: null, isAuthenticated: false, isLoading: false });
        }
      } else {
        clearTokens();
        set({ token: null, refreshToken: null, user: null, isAuthenticated: false, isLoading: false });
      }
    }
  },

  login: async (email, password) => {
    const tokens = await loginApi(email, password);
    persistTokens(tokens);
    set({ token: tokens.access_token, refreshToken: tokens.refresh_token });
    const user = await getMeApi();
    set({ user, isAuthenticated: true });
  },

  register: async (email, password, fullName, orgName) => {
    const tokens = await registerApi(email, password, fullName, orgName);
    persistTokens(tokens);
    set({ token: tokens.access_token, refreshToken: tokens.refresh_token });
    const user = await getMeApi();
    set({ user, isAuthenticated: true });
  },

  logout: () => {
    clearTokens();
    set({ token: null, refreshToken: null, user: null, isAuthenticated: false });
  },

  refresh: async () => {
    const rt = get().refreshToken;
    if (!rt) return null;
    try {
      const tokens = await refreshApi(rt);
      persistTokens(tokens);
      set({ token: tokens.access_token, refreshToken: tokens.refresh_token });
      return tokens.access_token;
    } catch {
      get().logout();
      return null;
    }
  },
}));
