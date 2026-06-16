import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // Target modern browsers to keep bundle lean
    target: "es2020",
    // Warn when an individual chunk exceeds 500 KB uncompressed (the real gate is
    // the ≤300 KB gzip measurement run in CI / Task 2 verify step).
    chunkSizeWarningLimit: 500,
    rollupOptions: {
      output: {
        // Split vendor (React, ReactDOM, router) into a separate chunk so the app
        // chunk stays small and only redownloads when app code changes.
        // Route-level React.lazy provides additional per-screen splits.
        // lucide-react: only named-import icons are used — tree-shaking handles it.
        // manualChunks as function (required by Vite 8 / rolldown)
        manualChunks(id: string) {
          if (id.includes("node_modules/react/") || id.includes("node_modules/react-dom/") || id.includes("node_modules/react-router-dom/")) {
            return "vendor";
          }
          if (id.includes("node_modules/i18next") || id.includes("node_modules/react-i18next")) {
            return "i18n";
          }
        },
      },
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
  },
});
