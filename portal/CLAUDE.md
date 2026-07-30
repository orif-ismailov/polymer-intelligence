# CLAUDE.md — portal/

Scoped guidance for `portal/` (the client cabinet SPA). See the repo-root `CLAUDE.md`
for the cross-cutting big picture.

## What this is

The **client cabinet** (R1): a person logs in by phone OTP, registers companies, submits
them for verification, and publishes offers — the browser counterpart to the staff
`dashboard/` and the Telegram `webapp/`. It is a **separate top-level app** served at the
root of `cabinet.ai-imex.com`. Distinct identity world from `webapp/` (Telegram `clients`/
`sellers`, frozen): the portal authenticates `user_accounts` (phone, passwordless OTP).

## Stack & tooling

Vite + React 18 + TypeScript (strict) · Tailwind · TanStack Query v5 · react-router-dom v7 ·
zustand · i18next (`react-i18next`). Run from `portal/`.

```bash
npm ci                 # install exact locked deps
npm run dev            # vite dev server (proxies /api → http://localhost:8000)
npm run lint           # eslint . --max-warnings 0
npm run typecheck      # tsc --noEmit
npm run build          # tsc -b tsconfig.build.json && vite build → dist/
npm run e2e            # playwright (needs a live API on :8000 + DEBUG=true console SMS)
#                        tip: OTP_DEV_CODE=000000 on that API fixes the login code so you can
#                        click through by hand; the specs read the real one via the peek hook
```

**Lockfile:** regenerate with `npx npm@10 install` — npm-11 lockfiles break Docker `npm ci`
in this repo (same constraint as `webapp/`/`dashboard/`).

## Layout — Feature-Sliced Design (`src/`)

| Layer | Role |
|------|------|
| `app/` | providers (QueryClient, i18n, router, theme), route tree, guards (`RequireAuth`, `RedirectIfAuthed`, `RequireCompany`). |
| `pages/` | login, otp, **onboarding** (the registration gate), home, companies, company-create (wizard + the done sheet), company-view, verification-status, offers, offer-edit, settings + **R2** market (grid + offer detail w/ inquiry form), inquiries (sent/incoming tabs + detail), requests (list + 4-step wizard + status-timeline detail), news (feed + article), notifications (full list) + **P6** samples (incoming/sent tabs), lab-orders (own analysis requests, read-only). |
| `widgets/` | `app-shell` (topbar + company switcher), `case-status-panel` (per-check chips + needs_info deep-links). |
| `features/` | auth-by-otp, company-wizard, submit-verification, upload-document, switch-company, offer-form + **R2** request-wizard, notification-center (topbar bell + dropdown, 30 s poll) + **P6** lab-passport (offer-form block: upload or order an analysis), sample-request (buyer form + both sides' actions). |
| `entities/` | account, company, verification, offer + **R2** market, inquiry, request, news, notification + **P5** compliance (substance picker data, verdicts, licences) + **P6** lab (orders + the two badges), sample (requests + status badge) — types + api hooks + zustand models. |
| `shared/` | `api` (fetch client + auth bridge), `ui` (Tailwind primitives), `lib` (phone mask, formatters), `config`, `i18n`. |

FSD import rule: a layer may import only from layers below it (`shared ⇐ entities ⇐ features
⇐ widgets ⇐ pages ⇐ app`). Never `shared → entities`.

## Notes specific to this package

- **Fetch client** (`shared/api/client.ts`): baseURL `/api/v1`, `credentials: "include"` (the
  httpOnly refresh cookie, path `/api/v1/portal`), attaches `Authorization: Bearer` from the
  in-memory token. Single-flight **401 → POST /portal/auth/refresh → retry-once**; a failed
  refresh clears auth + hard-redirects to `/login`. It stays business-agnostic via
  `shared/api/authBridge.ts` — the account store registers `getToken/setToken/clear` at boot,
  so `shared` never imports `entities`.
- **Access token in memory only** (never localStorage — XSS). Session continuity is the refresh
  cookie + a boot-time refresh; a full reload re-mints from the cookie.
- **Active company** id is persisted in localStorage (`entities/company/model/activeCompanyStore`);
  the topbar switcher scopes all company-scoped data. Selection self-heals if the id disappears.
- **build** is `tsc -b tsconfig.build.json && vite build` — a bare `tsc -b` on a `noEmit`
  composite hits TS6310, so the composite build has its own project (`tsconfig.build.json`);
  `tsconfig.json` is the plain app config for `tsc --noEmit` (typecheck).
- **i18n** locales `ru`/`uz`/`en` (ru primary) under `shared/i18n/locales/` — keep the key trees
  identical across all three (a missing key is a runtime error). No fa/zh here (portal launch set).
- **API base is relative** (`/api/v1`): dev = vite proxy → :8000; prod = nginx same-origin at
  `cabinet.ai-imex.com` (no CORS). Don't hardcode absolute API URLs.
- **Enforcement is badge-only in R1**: publishing requires a *verified* company (backend 403
  `company_not_verified`), surfaced as a locked offer form. No other gates are flipped.
- **Registration is the gate, not a page in the cabinet.** `RequireCompany` sends an account with
  zero companies to `/onboarding`; `/onboarding` and `/companies/new/*` are authenticated but sit
  OUTSIDE both `AppShell` and that guard (gating the screen that resolves "you have no company"
  on having one would loop). The flow follows `docs/new-design/register.jpeg`:
  **1 Тип компании (+ «Электронная подпись») → 2 Данные → 3 Банк → 4 Документы → 5 Проверка →
  «Регистрация завершена!»** (`/companies/new/done/:companyId`).
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

Static bundle → `portal_static` volume via `make portal-bundle` (= the profile-`build`
`portal-build` compose service, `deploy/Dockerfile.portal`). nginx serves it at the root of
`cabinet.ai-imex.com` + proxies `/api/` → `api:8000` same-origin. Prod TLS terminates on the
host front door (behind-proxy topology — see `deploy/CLAUDE.md`).

CI does the whole path on a push to `main`/`dev`: the `portal` job (lint · tsc · vite build)
gates `build-images`, which pushes `…-portal:<branch>`, and the deploy job pulls it and runs
`portal-build` so `portal_static` is refreshed on every deploy. **The bundle is not part of any
long-running image** — a deploy that skips `portal-build` leaves the previous cabinet build (or,
on a fresh server, an empty volume that answers 404).

Two things a request needs that live OUTSIDE this repo's containers, and both are ops steps:
`cabinet.ai-imex.com` DNS, and a **host** nginx vhost forwarding it to `127.0.0.1:8080` —
the inner nginx routes by `Host`, so a domain with no host-side block never reaches it
(`deploy/nginx/host-vhost.ai-imex.conf.example` now ships that block; certbot covers the name).

The bundle needs no build-time env or secrets: the API base is the relative `/api/v1`. Nothing
dev-only ships — `/dev/ui` is behind `import.meta.env.DEV`, and there is no client for the
`otp/peek` test hook.
