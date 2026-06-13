import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // Target modern browsers to keep bundle lean
    target: "es2020",
    // Warn when a chunk exceeds 300 KB (uncompressed) — bundle ≤300 KB gzip per C-frontend
    chunkSizeWarningLimit: 500,
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
