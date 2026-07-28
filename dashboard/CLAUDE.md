# CLAUDE.md — dashboard/

Scoped guidance for `dashboard/` (the internal team dashboard). See the repo-root
`CLAUDE.md` for the cross-cutting big picture.

## Stack & tooling

Next.js 16 (App Router) · React 18 · TypeScript · TanStack Query/Table · Tailwind + shadcn ·
`next-intl`. Run from `dashboard/`.

```bash
npm ci
npm run dev        # next dev (proxies /api/* → BACKEND_ORIGIN, default http://localhost:8000)
npm run lint       # eslint, --max-warnings 0
npm run typecheck  # tsc --noEmit
npm run e2e        # Playwright
npx next typegen   # regenerate typed-route defs before tsc on a clean checkout (CI does this)
```

## Layout

| Path | Role |
|------|------|
| `app/[locale]/...` | Localized App Router tree. The `(dashboard)/` route group holds the authed pages — signal side: `feed`, `signals`, `offers`, `prices`, `requests`, `sources`, `alerts`; marketplace/sourcing: `moderation`, `offer-requests`, `sourcing`, `partners`, `inventory`, `intel`, `substances` (the regulated-chemistry registry — admin writes, analyst reads); news: `reports`, `admin/news`; plus `admin/users` and `admin/products`. `login/` is outside the group. |
| `app/layout.tsx`, `app/[locale]/layout.tsx` | Root + locale shells. |
| `components/ui/` | shadcn primitives. `components/<domain>/` | feature components (feed, requests, sources, alerts, prices). `components/shared/` | cross-page chips/cards (`KindChip`, `StatusChip`, `UrgencyChip`, `KpiCard`). `components/layout/` | AppShell, Sidebar, LanguageSwitcher. |
| `hooks/` | `useSSE.ts` (live feed), `useAuth.ts`, `useDashboardSummary.ts`. |
| `lib/` | `api.ts` (fetch wrapper on the relative `/api/v1` base), `tz.ts` (Asia/Tashkent display), `queryClient.ts`, `utils.ts`. |
| `i18n/` | `routing.ts`, `request.ts`, `navigation.ts` (next-intl wiring). `messages/` | `ru`/`uz`/`tr`/`fa`/`zh` JSON. |
| `e2e/` | Playwright specs (the `dashboard-e2e` CI job). |
| `next.config.mjs` | `output: "standalone"`, next-intl plugin, dev `/api/*` rewrite. |
| `middleware.ts` | next-intl locale routing. |

## Notes specific to this package

- **API base is relative** (`/api/v1`): in prod nginx serves dashboard + backend same-origin (no
  CORS); in dev `next.config.mjs` rewrites `/api/*` → `BACKEND_ORIGIN`. Don't hardcode absolute API URLs.
- **Locales** `ru`/`uz`/`tr`/`fa`/`zh` (ru primary). Add UI strings to all five `messages/*.json`.
- **Live feed** is SSE via `hooks/useSSE.ts` (backend `feed_bus`), not polling.
- **News Engine admin** lives at `admin/news` (runtime settings, per-article approval queue, news-ops
  stats, run-parser trigger + live activity panel, AI-status health, edit-source) and `reports`
  (generate/approve/publish the daily & evening briefs). These back the backend `/admin/settings`,
  `/admin/news/*`, and `/admin/reports` routes.
- `next typegen` must run before `tsc` on a clean checkout — `.next/types/routes.d.ts` is gitignored
  and `next-env.d.ts` imports it (CI runs typegen explicitly).
- Time: store UTC, display Asia/Tashkent via `lib/tz.ts` — mirror of backend `app/core/time.py`.
- Prod image: `deploy/Dockerfile.dashboard` (Next standalone); served behind nginx at `/dashboard/`.
- e2e (`dashboard-e2e` CI job) runs Playwright against a live migrated+seeded API on :8000.
