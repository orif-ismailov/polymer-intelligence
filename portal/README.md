<!-- generated-by: gsd-doc-writer -->
# Polymer Intelligence — Portal

Part of the [Polymer Intelligence](../README.md) monorepo. See the root
[`README.md`](../README.md) and [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for the
system-wide picture.

The portal is the client cabinet: a React 18 + Vite app, server-side rendered, that serves two
distinct surfaces from one codebase:

- **A public marketplace** — storefront pages (`/`, `/market`, `/market/:offerId`,
  the four company directories, `/prices`, `/news`) rendered to real HTML so search engines
  index them. These read the unauthenticated `/api/v1/public/*` API surface.
- **The client cabinet** — phone-OTP login (`user_accounts`, distinct from the Telegram
  `webapp/` identity world), company registration + E-IMZO verification, offer/inquiry/request
  management, contracts and deals. These routes are client-rendered only and marked `noindex`.

The storefront is open to **everyone**: a session is what lets you act (inquiry, RFQ, chat,
publish), not what lets you read, so a listing has one address for a buyer, a seller and a
crawler alike. Signing in swaps the chrome — «Войти»/«Регистрация» become a «Кабинет» link —
and points the page's action CTAs into the cabinet; it does not move you off the page.

For deep implementation notes (FSD import rules, the auth/token model, the design-system
conventions, deploy topology) see [`portal/CLAUDE.md`](CLAUDE.md) — this README only covers
orientation and day-to-day commands.

## Stack

React 18 (TypeScript, strict) · Vite 6 · Express (SSR server) · react-router-dom v7 ·
TanStack Query v5 · zustand · i18next (`react-i18next`) · Tailwind CSS · Feature-Sliced Design.

## Install

```bash
cd portal
npm ci
```

Regenerate the lockfile with `npx npm@10 install` if you touch dependencies — an npm-11
lockfile breaks `npm ci` in the Docker build (same constraint as `webapp/`/`dashboard/`).

## Development

The portal is **server-rendered**, not a pure SPA — `npm run dev` starts the same
`server.js` Express process used in production, running Vite in middleware mode for HMR:

```bash
npm run dev     # SSR dev server on :5173, proxies /api → http://127.0.0.1:8000
```

It expects a FastAPI backend reachable at `127.0.0.1:8000` (see the root
[`README.md`](../README.md) / [`docs/GETTING-STARTED.md`](../docs/GETTING-STARTED.md) for how
to run it, e.g. `docker compose -f deploy/docker-compose.dev.yml up`). The dev proxy is
configured in `vite.config.ts`.

## Build & run (SSR)

```bash
npm run build     # tsc -b tsconfig.build.json && vite build (client) && vite build --ssr (server)
npm start          # node server.js against the built dist/ (NODE_ENV=production)
npm run preview    # build + run with an optional /api dev proxy (DEV_API_PROXY=1), for local sanity checks
```

`npm run build` produces two bundles side by side under `dist/`: `dist/client` (served to the
browser) and `dist/server` (imported by `server.js` to render). Both are required — either
alone is an incomplete deploy. In production, `deploy/Dockerfile.portal` builds a runnable Node
image and the `portal` compose service runs `node server.js` on port 3000; nginx proxies
`cabinet.ai-imex.com` to it (the bundle is a long-running service, not a static file volume).
`server.js` also serves `robots.txt` and a dynamically generated `sitemap.xml` (sourced from
`GET /api/v1/public/sitemap`).

## Layout — Feature-Sliced Design (`src/`)

| Layer | Contains |
|---|---|
| `app/` | providers (QueryClient, i18n, router, theme), route tree (`app/router/routes.tsx`), guards (`RequireAuth`, `RedirectIfAuthed`, `RequireCompany`). |
| `pages/` | route-level screens: `login`/`otp`, `onboarding` (registration gate), `home`, `companies`/`company-view`/`company-create`, `verification-status`, `offers`/`offer-create`, `settings`, `market`, `inquiries`, `requests`, `news`, `notifications`, `samples`, `lab-orders`, `deals`, `contracts`, plus the public counterparts `public-home`, `public-market`, `public-directory`, `public-prices`. |
| `widgets/` | composed UI blocks: `app-shell` (cabinet topbar + sidebar + company switcher), `public-shell` (storefront nav + footer, session-aware), `case-status-panel`. |
| `features/` | user-facing flows: `auth-by-otp`, `company-profile`, `company-wizard`, `deal-room`, `eimzo-sign`, `factory-rfq`, `manufacturer-chat`, `notification-center`, `offer-wizard`, `product-detail`, `request-wizard`, `rfq-response`, `sample-request`, `submit-verification`, `switch-company`, `upload-document`. |
| `entities/` | domain types + API hooks + zustand models: `account`, `company`, `compliance`, `contract`, `deal`, `inquiry`, `lab`, `manufacturer`, `market`, `news`, `notification`, `offer`, `product`, `request`, `sample`, `verification`, `public` (public-surface data). |
| `shared/` | `api` (fetch client + auth bridge), `ui` (Tailwind primitives), `lib`, `config`, `i18n`, `seo`. |

Additionally, `src/entry-client.tsx` / `src/entry-server.tsx` are the two hydration/render
entry points, and `src/ssr/` holds SSR-specific rendering helpers. `server.js` at the package
root is the Express SSR server (dev and prod share the same file).

FSD import rule: a layer may import only from layers below it —
`shared ⇐ entities ⇐ features ⇐ widgets ⇐ pages ⇐ app`.

## Routing: public vs. authenticated

Defined in `src/app/router/routes.tsx`, in two namespaces.

1. **Public storefront** at the root (`PublicShell`), open to everyone:
   `/`, `/market`, `/market/:offerId`, `/prices`, `/news`, `/news/:signalId`, and the four
   company directories (`manufacturers`/`traders`/`logistics`/`laboratories`, each with a
   `/:companyId` profile — slugs come from `PUBLIC_DIRECTORIES` in
   `src/shared/config/publicRoutes.ts`). These are the crawlable URLs and the only ones that
   are server-rendered. **No guard sits on them**: a session changes the chrome and the
   action CTAs, never the URL.
2. **Cabinet** under `/cabinet`: auth screens (`/cabinet/login`, `/cabinet/login/code`)
   behind `RedirectIfAuthed`; `/cabinet/onboarding` and `/cabinet/companies/new/*` (the
   registration flow, deliberately outside the shell and outside `RequireCompany`); then
   everything else behind `RequireAuth` + `RequireCompany` inside `AppShell`.

The prefix exists to keep the two namespaces from colliding — `/market/favorites` no longer
has to out-rank `/market/:offerId`, `/manufacturers/:id/chat` no longer has to out-rank the
public directory's `:companyId`. The cabinet still **mirrors part of the storefront's shape**
(`/cabinet/market/:offerId`, `/cabinet/prices`, `/cabinet/news`, `/cabinet/traders/:companyId`),
a duplication that is being collapsed onto the public URL page by page. On top of it sit the
cabinet-only surfaces:
`/cabinet/offers`, `/deals`, `/contracts`, `/inquiries`, `/requests`, `/samples`,
`/lab-orders`, `/notifications`, `/companies`, `/settings`, `/market/requests`,
`/market/favorites`, `/sellers/:companyId`, `/manufacturers/:companyId/chat`,
`/manufacturers/:companyId/rfq/:offerId` (all under `/cabinet`).

Pages mounted in **both** namespaces (news, prices, the three read-only directories) are one
component; their internal links go through `shared/lib/useTierBase()`.

Crossing between the two: the storefront header shows a «Кабинет» link once there is a
session (`PublicTopNav`), the cabinet sidebar has a «Маркетплейс» link back to `/`
(`SideNav`), and the **brand lockup points at `/` from every surface that draws it** —
cabinet topbar, login/OTP, onboarding, storefront footer. A public action CTA
(«Отправить запрос», «Связаться») goes straight to its
cabinet destination when signed in, and to `/cabinet/login` carrying that destination as
`state.from` when not — so signing in from a listing returns you to *that listing*.

Root-level cabinet URLs from before the prefix (`/login`, `/companies/…`, `/offers/…`)
**301** to their `/cabinet` equivalent from `server.js`.

`src/shared/config/publicRoutes.ts` also exports `SERVER_RENDERED_PATTERNS` /
`isServerRenderedPath`, which `server.js` mirrors as a literal `PUBLIC_PATTERNS` regex list
(the server has no bundle to import from at boot, so the pattern is duplicated there — keep
both in sync). A path outside that list gets only the app shell from `server.js`
(`noindex,nofollow`) and renders entirely client-side.

## i18n

Locales live under `src/shared/i18n/locales/`: **`ru`** (primary), **`uz`**, **`en`** — no
`fa`/`zh` here (unlike `webapp/`). Key trees must stay identical across all three; a missing
key is a runtime error, not a silent fallback. The SSR server resolves the render language per
request (`?lang=` → `portal.language` cookie → `Accept-Language` → `ru`) so hydration doesn't
mismatch — see `resolveLang` in `server.js`.

## Configuration / env vars

The client bundle takes **no build-time env vars** — the API base is always the relative
`/api/v1` (dev: Vite proxy to `:8000`; prod: nginx same-origin on `cabinet.ai-imex.com`, no
CORS). Two **runtime** env vars are read by `server.js` (not `VITE_*`, not baked into the
bundle):

| Var | Meaning |
|---|---|
| `INTERNAL_API_ORIGIN` | Where the SSR render reaches the API. `http://api:8000` under compose; defaults to `http://127.0.0.1:8000`. |
| `PUBLIC_SITE_ORIGIN` | Absolute origin used for canonical URLs / `og:url` / `sitemap.xml`. Empty derives it per request from the forwarded host (fine for dev); **must be set in production**. |

`PORT` (default `3000`, overridden to `5173` by `npm run dev`), `NODE_ENV`, and
`DEV_API_PROXY=1` (opt-in same-origin `/api` proxy for `npm run preview`, standalone-only) are
also read by `server.js`. See [`docs/CONFIGURATION.md`](../docs/CONFIGURATION.md) for the
backend's env contract.

## Quality gates

```bash
npm run lint        # eslint . --max-warnings 0
npm run typecheck    # tsc --noEmit
npm run build        # tsc -b tsconfig.build.json && vite build (client + server) — also gates CI
npm run e2e          # playwright; needs a live API on :8000 + DEBUG=true for console-logged OTP codes
```

These are the same checks the `portal` job runs in `.github/workflows/ci.yml` (lint · tsc ·
vite build), which gates the `build-images` job. See [`docs/TESTING.md`](../docs/TESTING.md)
for the project-wide testing approach.

## Further reading

- [`portal/CLAUDE.md`](CLAUDE.md) — full component guide: FSD conventions, auth/token model,
  the registration-wizard flow, design-system rules, and deploy topology.
- [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) — system-wide architecture.
- [`docs/CONFIGURATION.md`](../docs/CONFIGURATION.md) — backend environment-variable contract.
- [`docs/DEVELOPMENT.md`](../docs/DEVELOPMENT.md) — repo-wide developer workflow and CI gates.
- [`docs/TESTING.md`](../docs/TESTING.md) — testing approach across components.
- [`docs/API.md`](../docs/API.md) — backend API reference.
- [`deploy/CLAUDE.md`](../deploy/CLAUDE.md) — docker-compose / nginx deploy topology.
