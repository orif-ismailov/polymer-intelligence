import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

// The portal is server-rendered for its public routes and client-rendered
// behind the login. In dev, `server.js` runs Vite in middleware mode and this
// config supplies the transform; the proxy below forwards `/api/v1` to the
// FastAPI backend on :8000 (same-origin from the browser's perspective, so the
// httpOnly refresh cookie flows).
export default defineConfig({
  base: "/",
  plugins: [react()],
  ssr: {
    // Build: bundle everything. `dist/server/entry-server.js` is imported by
    // server.js as a plain ES module, so it must not be left with bare
    // specifiers Node cannot resolve relative to the bundle.
    noExternal: process.env.SSR_BUILD ? true : undefined,
    // react-router 7 ships ESM, but only behind the `module-sync` / `module`
    // export conditions: under plain `node` its default is the CommonJS build.
    // Vite's dev SSR resolver picks that CJS file, Node cannot read named
    // exports off it, and every dev render died on
    // `Named export 'Navigate' not found` then silently fell back to the
    // client-only shell (a 200 with an empty <div id="root">, which is exactly
    // the failure this whole change exists to prevent, and it would have looked
    // fine in a browser). Asking for the ESM condition fixes it without
    // inlining the dependency.
    resolve: {
      conditions: ["module-sync", "module", "import", "node", "default"],
      externalConditions: ["module-sync", "module", "import", "node", "default"],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(rootDir, "src"),
    },
  },
  build: {
    // Two builds land side by side: `dist/client` is what the browser gets and
    // what nginx/sirv serves, `dist/server` is the bundle server.js imports to
    // render. `npm run build` runs both; either alone is an incomplete deploy.
    outDir: process.env.SSR_BUILD ? "dist/server" : "dist/client",
    target: "es2022",
    sourcemap: false,
    chunkSizeWarningLimit: 600,
    // The client build must emit a manifest-shaped index.html for the server to
    // use as its template.
    ssrManifest: !process.env.SSR_BUILD,
    rollupOptions: {
      output: {
        manualChunks(id: string): string | undefined {
          // Chunk splitting only applies to the browser build. Splitting the
          // SSR bundle just adds imports for Node to resolve at boot.
          if (process.env.SSR_BUILD) return undefined;
          if (
            id.includes("node_modules/react/") ||
            id.includes("node_modules/react-dom/") ||
            id.includes("node_modules/react-router")
          ) {
            return "vendor-react";
          }
          if (id.includes("node_modules/@tanstack/")) {
            return "vendor-query";
          }
          if (id.includes("node_modules/i18next") || id.includes("node_modules/react-i18next")) {
            return "vendor-i18n";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
    // Prefer IPv4 explicitly: on macOS `localhost` resolves to ::1 first, while
    // local uvicorn often binds only 127.0.0.1 — the proxy then fails and every
    // `/api` call surfaces as a generic "Failed to fetch" in the SPA.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
