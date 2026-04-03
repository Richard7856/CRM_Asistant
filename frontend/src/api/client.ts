/**
 * Axios instance with JWT auth interceptor.
 * Automatically attaches Bearer token from authStore and handles
 * 401 responses by attempting a silent token refresh.
 */

import axios from "axios";

const apiClient = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

// --- Request interceptor: attach JWT if available ---
apiClient.interceptors.request.use((config) => {
  // Lazy import to avoid circular dependency — authStore imports apiClient
  const token = localStorage.getItem("crm_access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// --- Response interceptor: handle 401 with silent refresh ---
let isRefreshing = false;
let refreshQueue: Array<(token: string) => void> = [];

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;

    // Skip refresh for auth endpoints to avoid infinite loops
    const isAuthEndpoint = original?.url?.startsWith("/auth/");

    if (error.response?.status === 401 && !original._retry && !isAuthEndpoint) {
      original._retry = true;

      // After proxy redirect, axios may resolve the URL to the backend's
      // absolute URL (e.g. http://localhost:8000/api/v1/...). Reset baseURL
      // so retries go through the Vite proxy again.
      if (original.baseURL !== "/api/v1") {
        original.baseURL = "/api/v1";
      }

      if (isRefreshing) {
        // Queue this request — it will be retried once refresh completes
        return new Promise((resolve) => {
          refreshQueue.push((newToken: string) => {
            original.headers.Authorization = `Bearer ${newToken}`;
            resolve(apiClient(original));
          });
        });
      }

      isRefreshing = true;

      try {
        // Dynamic import to break circular dependency
        const { useAuthStore } = await import("@/stores/authStore");
        const newToken = await useAuthStore.getState().refresh();

        if (newToken) {
          // Retry queued requests
          refreshQueue.forEach((cb) => cb(newToken));
          refreshQueue = [];
          isRefreshing = false;

          original.headers.Authorization = `Bearer ${newToken}`;
          return apiClient(original);
        }
      } catch {
        // Refresh failed — logout handled inside store.refresh()
      }

      refreshQueue = [];
      isRefreshing = false;
    }

    const message =
      error.response?.data?.detail || error.message || "An error occurred";
    console.error("API Error:", message);
    return Promise.reject(error);
  },
);

export default apiClient;
