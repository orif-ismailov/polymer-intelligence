/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
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

export default nextConfig;
