import createNextIntlPlugin from "next-intl/plugin";

// Wires the next-intl request config (./i18n/request.ts) into the build.
const withNextIntl = createNextIntlPlugin();

// Content-Security-Policy for every dashboard page (audit IMEX-06). The staff UI is
// where a stored-XSS payload would be worth the most, so the browser is told to run
// nothing that is not ours even if some future render forgets to escape. Everything
// here is same-origin: the API is proxied under /api, fonts are self-hosted by
// next/font, and protected images arrive as blob: URLs (see lib/api.ts). Presigned
// document links open as top-level navigations, which CSP does not govern.
// 'unsafe-inline' scripts: the App Router inlines its bootstrap without a nonce.
// 'unsafe-eval' in development only: React Refresh needs it.
const isDev = process.env.NODE_ENV !== "production";
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No `X-Powered-By: Next.js` — a free framework fingerprint (audit IMEX-09).
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [{ key: "Content-Security-Policy", value: contentSecurityPolicy }],
      },
    ];
  },
  // Output as standalone for Docker deployment
  output: "standalone",
  // Dev-only API proxy: api.ts calls the backend at the relative "/api/v1" base,
  // which only resolves same-origin (nginx serves dashboard + backend in prod).
  // Under `next dev` there is no same-origin backend, so proxy /api/* to the
  // FastAPI dev server (deploy/docker-compose.dev.yml publishes it on :8000).
  // Server-side rewrite → no CORS config needed; also covers the SSE feed.
  // Override the target with BACKEND_ORIGIN if your API runs elsewhere.
  async rewrites() {
    const backend = process.env.BACKEND_ORIGIN || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default withNextIntl(nextConfig);
