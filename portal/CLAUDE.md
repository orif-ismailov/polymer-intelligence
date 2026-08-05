# CLAUDE.md — portal/

Scoped guidance for `portal/` (the client cabinet SPA). See the repo-root `CLAUDE.md`
for the cross-cutting big picture.

## What this is

Two surfaces in one app, split by whether a page needs a session.

**The public marketplace** (R7): the storefront at `/`, `/market`, `/market/:offerId`, the
four company directories (`/manufacturers`, `/traders`, `/logistics`, `/laboratories`, each
with a `/:companyId` profile), `/prices` and `/news`. These routes are **server-rendered**
so search engines receive real HTML, and they read `/api/v1/public/*`, the only API surface
with no auth dependency. Open to **everyone**, signed in or not.

**The client cabinet** (R1): everything under **`/cabinet`** — a person logs in by phone
OTP, registers companies, submits them for verification, and publishes offers. The browser
counterpart to the staff `dashboard/` and the Telegram `webapp/`. Distinct identity world
from `webapp/` (Telegram `clients`/`sellers`, frozen): the portal authenticates
`user_accounts` (phone, passwordless OTP). Cabinet routes are **client-rendered only** and
`noindex`, which is now one line of robots.txt (`Disallow: /cabinet`) rather than a list
that kept drifting.

Both are served from `cabinet.ai-imex.com`. The marketplace has not moved to the apex
domain yet — that decision is open, and the code is written so it is one env var
(`PUBLIC_SITE_ORIGIN`) plus an nginx vhost, never a rebuild.

### The two namespaces

The cabinet is everything behind a session. The storefront is **not** its anonymous
counterpart — it is the public face of the same marketplace, and a signed-in visitor
browses it like anyone else. What a session buys is the ability to **act** (send an
inquiry, open an RFQ, chat with a factory, publish an offer), not the ability to **read**,
which is also the only version of these pages that can rank. So `/market/1204` is one
address for a buyer, a seller and a crawler.

A guard (`RedirectAuthedToCabinet`) used to bounce signed-in visitors to the `/cabinet`
twin of whatever they opened. It is **deleted** — do not reintroduce it. The chrome carries
the session instead: `PublicTopNav` swaps «Войти»/«Регистрация» for a single «Кабинет»
link, the cabinet's `SideNav` has a «Маркетплейс» link back out, and every `BrandLogo` on
the site is wrapped in a link to `/` — cabinet topbar, login/OTP, onboarding, footer. The
lockup is the marketplace's front door from everywhere; the cabinet home has its own nav
entry and does not need the logo too. An anonymous CTA («Отправить запрос», «Связаться»)
goes through `/cabinet/login` with `state.from` set to **the page it was clicked on**, so
signing in from a listing returns you to *that listing* — where the real actions are now
waiting.

**The product sheet and the company profile have no cabinet twin.** `/market/:offerId` and
`/{directory}/:companyId` are the only ones, for everyone: `/cabinet/market/:offerId` and
`/cabinet/manufacturers/:companyId` were deleted and now redirect (notification payloads
still carry the old URLs). The signed-in surface — inquiry form, favourite, «Мои запросы»,
the contract/escrow bar, sample requests, the factory chat/RFQ entry — mounts **on those
same pages**, and only after hydration.

That is the rule to understand before touching a public page. What may vary by session is
what renders **after** hydration; what may never vary is the **server render**.
`selectIsAuthenticated` is `token !== null`, false during SSR and at first paint, so the
server always emits the anonymous markup and the session surface arrives as a state change
rather than a hydration mismatch. That HTML is shared-cached (`s-maxage=60`) precisely
because nothing in it varies by visitor — an `e2e/public-authed.spec.ts` case asserts an
anonymous listing carries no acting controls at all.

The mechanism is `useOfferSession` (`features/product-detail`): it gates every authed query
on `selectIsAuthenticated` and returns `null` until they settle, so a caller reads it as
"there is nobody to act as (yet)". Follow it for any new session surface — and note that a
hook without an `enabled` guard fires from **Node** during SSR, which is how
`useCompanies()` was quietly issuing `GET /portal/companies` on every public render before
it took an `enabled` argument.

What the `/cabinet` prefix earns is collision-freedom. Before it, cabinet pages lived
inside public namespaces and had to be held apart by declaration order and comments:
`/market/favorites` had to out-rank `/market/:offerId`, and `/manufacturers/:id/chat` had
to out-rank the public directory's `:companyId`. Now no public path can be shadowed by a
cabinet one.

Some pages are still mounted in **both** tiers because they read the same either way — the
news reader, the price table, the three non-manufacturer directories. They are one
component, and their internal links go through `shared/lib/useTierBase()`, which returns
`"/cabinet"` or `""` for the tier they are currently rendering in; hardcoding a path in one
of those is the mistake to watch for. That duplication is **temporary** — it is being
collapsed onto the single public URL page by page (the market and manufacturer sheets went
first), so don't add new twins. A link to a listing is the exception that is already
settled: it is always `/market/:id`, never `${base}/market/:id`, because there is only one.

Old root-level cabinet URLs (`/login`, `/companies/…`, `/offers/…`) **301 to their
`/cabinet` equivalent** from `server.js`, not from the router: `entry-server.tsx` returns
only a status and drops the router's `Location`, so an SSR-time `redirect()` would land on
the home page.

## Stack & tooling

Vite + React 18 + TypeScript (strict) · Tailwind · TanStack Query v5 · react-router-dom v7 ·
zustand · i18next (`react-i18next`). Run from `portal/`.

```bash
npm ci                 # install exact locked deps
npm run dev            # SSR dev server on :5173 (Vite middleware, proxies /api → :8000)
npm start              # production: node server.js against dist/ (needs npm run build first)
npm run lint           # eslint . --max-warnings 0
npm run typecheck      # tsc --noEmit
npm run build          # tsc -b tsconfig.build.json && vite build (client) && vite build --ssr (server) → dist/
npm run e2e            # playwright (needs a live API on :8000 + DEBUG=true console SMS)
#                        tip: OTP_DEV_CODE=000000 on that API fixes the login code so you can
#                        click through by hand; the specs read the real one via the peek hook
```

**Lockfile:** regenerate with `npx npm@10 install` — npm-11 lockfiles break Docker `npm ci`
in this repo (same constraint as `webapp/`/`dashboard/`).

## Layout — Feature-Sliced Design (`src/`)

| Layer | Role |
|------|------|
| `app/` | providers (QueryClient, i18n, router, theme), route tree, guards (`RequireAuth`, `RedirectIfAuthed`, `RequireCompany`) — all three cabinet-side; the storefront has none. |
| `pages/` | login, otp, **onboarding** (the registration gate), home, companies, company-create (wizard + the done sheet), company-view, verification-status, offers, offer-create, settings + **R2** market (favorites + RFQ inbox only — the grid and the offer sheet are public now), inquiries (sent/incoming tabs + detail), requests (list + 4-step wizard + status-timeline detail), news (feed + article), notifications (full list) + **P6** samples (incoming/sent tabs), lab-orders (own analysis requests, read-only). |
| `widgets/` | `app-shell` (topbar + company switcher), `case-status-panel` (per-check chips + needs_info deep-links). |
| `features/` | auth-by-otp, company-wizard, submit-verification, upload-document, switch-company, offer-form + **R2** request-wizard, notification-center (topbar bell + dropdown, 30 s poll) + **P6** lab-passport (offer-form block: upload or order an analysis), sample-request (buyer form + both sides' actions). |
| `entities/` | account, company, verification, offer + **R2** market, inquiry, request, news, notification + **P5** compliance (substance picker data, verdicts, licences) + **P6** lab (orders + the two badges), sample (requests + status badge) — types + api hooks + zustand models. |
| `shared/` | `api` (fetch client + auth bridge), `ui` (Tailwind primitives), `lib` (phone mask, formatters, `useTierBase`), `config` (incl. `CABINET_BASE`/`isCabinetPath`), `i18n`. |

FSD import rule: a layer may import only from layers below it (`shared ⇐ entities ⇐ features
⇐ widgets ⇐ pages ⇐ app`). Never `shared → entities`.

## Notes specific to this package

- **Fetch client** (`shared/api/client.ts`): baseURL `/api/v1`, `credentials: "include"` (the
  httpOnly refresh cookie, path `/api/v1/portal`), attaches `Authorization: Bearer` from the
  in-memory token. Single-flight **401 → POST /portal/auth/refresh → retry-once**; a failed
  refresh clears auth + hard-redirects to `/cabinet/login` — and only from inside the cabinet
  (`isCabinetPath`), because on the storefront a 401 is the normal state of most visitors. It
  stays business-agnostic via
  `shared/api/authBridge.ts` — the account store registers `getToken/setToken/clear` at boot,
  so `shared` never imports `entities`.
- **Access token in memory only** (never localStorage — XSS). Session continuity is the refresh
  cookie + a boot-time refresh; a full reload re-mints from the cookie.
- **Active company** id is persisted in localStorage (`entities/company/model/activeCompanyStore`);
  the topbar switcher scopes all company-scoped data. Selection self-heals if the id disappears.
- **build** is `tsc -b tsconfig.build.json && npm run build:client && npm run build:server` —
  a bare `tsc -b` on a `noEmit` composite hits TS6310, so the composite build has its own
  project (`tsconfig.build.json`); `tsconfig.json` is the plain app config for `tsc --noEmit`
  (typecheck). `build:client` is `vite build` (the client bundle); `build:server` is
  `vite build --ssr src/entry-server.tsx` (the SSR render bundle `server.js` loads).
- **i18n** locales `ru`/`uz`/`en` (ru primary) under `shared/i18n/locales/` — keep the key trees
  identical across all three (a missing key is a runtime error). No fa/zh here (portal launch set).
- **API base is relative** (`/api/v1`): dev = vite proxy → :8000; prod = nginx same-origin at
  `cabinet.ai-imex.com` (no CORS). Don't hardcode absolute API URLs.
- **Enforcement is badge-only in R1**: publishing requires a *verified* company (backend 403
  `company_not_verified`), surfaced as a locked offer form. No other gates are flipped.
- **Registration is the gate, not a page in the cabinet.** `RequireCompany` sends an account with
  zero companies to `/cabinet/onboarding`; that route and `/cabinet/companies/new/*` are
  authenticated but sit OUTSIDE both `AppShell` and that guard (gating the screen that resolves "you have no company"
  on having one would loop). The flow follows `docs/new-design/register.jpeg`:
  **1 Тип компании (+ «Электронная подпись») → 2 Данные → 3 Банк → 4 Документы → 5 Проверка →
  «Регистрация завершена!»** (`/cabinet/companies/new/done/:companyId`).
  - The four account types are the mockup's, not the backend enum: `buyer→importer`,
    `supplier→distributor` are the nearest members that exist (`ACCOUNT_TYPES` in
    `features/company-wizard/model/constants.ts`). Sending anything else 422s — the enum is a
    Postgres type, so widening it is a migration.
  - **Signing comes before the form on purpose.** The challenge endpoint is company-scoped, so
    `companyRegistrationSigner` reads the STIR out of the chosen certificate's subject, creates the
    company from it, then signs — which is why `EimzoSigner.getChallenge` takes the certificate.
    A signed company arrives at step 2 filled in and `identity_locked` (those fields render
    disabled, and `useSubmitWizard` omits them from the PATCH or the server 409s).
  - **Arriving at step 5 IS the submit** — there is no confirmation sheet. It is guarded by a ref
    against React's double mount, and the checks then poll until they resolve.
  - Bank + documents are not in the mockup but feed the case's `bank_requisites` /
    `documents_complete` checks, so they keep their place in the flow wearing the same chrome.
- **Design system (P0 — `docs/design-system.md` Part II).** The portal follows the IMEX AI
  mockups in `docs/new-design/`; **dark is the default theme**, light is secondary.
  - Build screens from `shared/ui` primitives and tokens **only**. No hex, no stock Tailwind
    palette (`blue-600`, `slate-800`), no `text-white` — a new colour is a new token in
    `src/app/styles.css` + `tailwind.config.ts`, never an inline value. Need a new look for a
    primitive? Add a variant to the primitive, don't restyle it at the call site.
  - Prefer semantic props: `<Badge variant="verified">` over hand-picking tone + icon.
  - **Page chrome comes from primitives.** `PageHeader` (back link + `h1` + badge + subtitle
    + actions), `Tabs`, `SpecList`/`SpecItem`, `SpecTile`, `FileRow`, `StickyActionBar`. If
    you are typing `text-2xl` or `<h1>` in a page file, you are re-implementing `PageHeader`
    — the type/spacing scale lives in those primitives and in `docs/design-system.md` §P6,
    deliberately NOT in `tailwind.config.ts` (a named utility renames the call-site decision
    instead of removing it, and no gate can see a font size).
  - A screen using `StickyActionBar` must add `pb-36 md:pb-0`; a grid column containing
    `Tabs` must have `min-w-0`. Both failure modes are invisible to the suite.
  - Numbers that line up in a column (prices, MOQ, volumes, metrics) get `.num`.
  - A colour class that changes nothing on screen probably **doesn't exist** in the config —
    that failure mode is silent. Same for a utility added to `tailwind.config.ts` without
    restarting `npm run dev`.
  - `/dev/ui` (DEV builds only) renders the whole kit on one page; it's both the visual
    reference and the fixture for `e2e/p0-ui-kit.spec.ts`. Add new primitives there.
  - The two `e2e/p0-*.spec.ts` specs gate the system (dark default, token contrast in both
    themes, rendered-label AA, primitive semantics). Keep them green; extend them when you
    add tokens or variants.

## Deploy

**The portal is a long-running service now, not a static bundle.** `deploy/Dockerfile.portal`
builds a runnable Node image; the `portal` compose service runs `server.js` on :3000, and
nginx *proxies* `cabinet.ai-imex.com` to it instead of serving `/var/www/portal`. Prod TLS
terminates on the host front door (behind-proxy topology — see `deploy/CLAUDE.md`).

Two runtime env vars, both read by `server.js`, neither baked into the bundle:

| Var | Meaning |
|---|---|
| `INTERNAL_API_ORIGIN` | Where the render reaches the API. `http://api:8000` under compose — a render must not leave the docker network and come back through nginx. |
| `PUBLIC_SITE_ORIGIN` | Absolute origin for canonical / `og:url` / `sitemap.xml`. Empty derives it per request from the forwarded Host, which is right for dev. **Set it in production**: a canonical that varies by request header is one a crawler cannot trust. |

Failure modes changed with the topology: the old symptom of a broken cabinet was a **404**
from an empty `portal_static` volume. It is now a **502** from the nginx proxy. Check
`docker compose ps portal` first. `make portal-bundle` keeps its name but now rebuilds and
restarts the service.

`robots.txt` and `sitemap.xml` are served by `server.js`, not by a static file: the sitemap
is generated per request from `GET /api/v1/public/sitemap`, and falls back to the static
section alone if the API is unreachable (a partial sitemap beats a 500).

CI does the whole path on a push to `main`/`dev`: the `portal` job (lint · tsc · vite build)
gates `build-images`, which pushes `…-portal:<branch>`. The deploy job's `docker compose pull`
+ `up -d` now refreshes the portal like any other service — the `portal-build` one-shot is
gone from both deploy jobs, and running it would fail on an undefined service.

Two things a request needs that live OUTSIDE this repo's containers, and both are ops steps:
`cabinet.ai-imex.com` DNS, and a **host** nginx vhost forwarding it to `127.0.0.1:8080` —
the inner nginx routes by `Host`, so a domain with no host-side block never reaches it
(`deploy/nginx/host-vhost.ai-imex.conf.example` now ships that block; certbot covers the name).

The bundle needs no build-time env or secrets: the API base is the relative `/api/v1`. Nothing
dev-only ships — `/dev/ui` is behind `import.meta.env.DEV`, and there is no client for the
`otp/peek` test hook.
