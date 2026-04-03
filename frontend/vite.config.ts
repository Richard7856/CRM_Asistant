import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Tailwind CSS v4 via PostCSS instead of Vite plugin
// — the @tailwindcss/vite plugin hangs on iCloud paths with spaces
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
    watch: {
      // iCloud paths with spaces cause native watchers to fire constantly
      // — polling with a long interval keeps HMR stable
      usePolling: true,
      interval: 2000,
    },
    hmr: {
      // Prevent HMR reconnect storms on iCloud paths
      overlay: false,
    },
  },
});
