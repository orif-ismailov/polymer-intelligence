# CLAUDE.md — webapp/

Scoped guidance for `webapp/` (the Telegram Web App / Mini App — the client
request-submission surface). See the repo-root `CLAUDE.md` for the big picture.

## Stack & tooling

React 18 + Vite · TypeScript · react-router · i18next · zustand · react-hook-form + zod ·
`@telegram-apps/sdk`. Run from `webapp/`.

```bash
npm ci
npm run dev        # vite dev server
npm run build      # tsc && vite build  → dist/
npm run lint       # eslint, --max-warnings 0
npm run typecheck  # tsc --noEmit
npm run e2e        # Playwright
```

## Layout

| Path | Role |
|------|------|
| `src/pages/` | `Landing` (public marketing `/`), request flow (`Home`, `MyRequests`, `RequestDetail`, `Notifications`, `Settings`, `Profile`) + `wizard/` steps (`Step1`–`Step4`, `Confirm`); marketplace (`Market`, `OfferDetail`, `MyInquiries`, `InquiryDetail`, `Sell`, `SellOffer`, `EditOffer`); news (`News`, `NewsArticle`, `NewsDetail`); info (`HowItWorks`, `Support`). |
| `src/store/` | `wizardStore.ts` (request wizard), `authStore.ts` (Mini-App vs. browser auth resolution), `roleStore.ts` (buyer/seller preference). |
| `src/api/client.ts` | API client; authenticates with the Telegram `initData` HMAC header (or browser cookie). Covers `/webapp/{auth,requests,me,reference,market,seller,news}` — incl. news cards `GET /webapp/news/articles[/{id}]` + `/filters`. |
| `src/telegram.ts` | Telegram WebApp SDK bootstrap (theme, initData). |
| `src/i18n/` | i18next setup + `ru`/`en`/`uz`/`tr`/`fa`/`zh` JSON (`SUPPORTED_LANGS`; `fa` is RTL). |
| `src/components/` | Shared UI (FieldGroup, FileUploader, StatusTimeline, StepIndicator, BottomTabBar, TopNav, IncotermsField, RadioCard, …). |
| `src/types.ts` | Shared types. `vite.config.ts` | build config. |
| `e2e/` | Playwright specs incl. a Telegram-env stub (`telegram.ts`) and cross-app spec. |

## Notes specific to this package

- **Dual-context**: runs both inside Telegram (Mini App) and in a plain browser.
  `telegram.isMiniApp()` (`isTMA('simple')`) is the signal. `store/authStore.ts` resolves
  auth at boot: Mini App → always authed (initData); browser → probes `GET /webapp/me`.
- **Auth**: Mini App sends `X-Telegram-Init-Data` (HMAC + TTL). Browser signs in via the
  **Telegram Login Widget** (`components/TelegramLoginGate.tsx`) → `POST /webapp/auth/telegram`
  sets an httpOnly `client_session` cookie; `api/client.ts` sends `credentials:"include"` and
  omits the empty initData header so the backend falls through to the cookie. Backend
  `get_current_client` accepts either. Browser login needs `BOT_USERNAME` + BotFather `/setdomain`.
- **Routing/chrome**: `/` is the public IMEX AI marketing landing (`pages/Landing.tsx`),
  full-bleed with its own header/footer — shown in both contexts.
  All other routes live under the `AppLayout` layout route (`App.tsx`) behind `RequireAuth`;
  responsive chrome switches mobile `BottomTabBar` ↔ desktop `TopNav` via `hooks/useIsDesktop`.
- **Landing** uses scoped CSS (`.imex-landing`, neon `#5CFF6E` on `#05070A`) + a tiny
  IntersectionObserver reveal (`hooks/useScrollReveal.ts`) — no Tailwind/Framer Motion (bundle budget).
  Marketplace cards come from the **public** `GET /webapp/market/featured` (no seller contacts).
- Built as a **static bundle** and served by nginx at the **root of `ai-imex.com`** (Vite
  `base: "/"`). Build + load into the `webapp_static` volume from the repo root with
  `make webapp-bundle` (`deploy/Dockerfile.webapp`). The bot's WebApp button points at
  `${PUBLIC_WEBAPP_URL}/`.
- **Scope**: beyond the request-submission wizard this app is now a full Mini-App surface — a
  marketplace (browse offers `/market`, submit inquiries `/inquiries`, publish/edit seller offers
  `/sell`) and a **news reader** (`/news` cards → `/news/article/:id`, plus `/news/:id` digest reports).
  The bottom-tab set is Market · Requests · Sell · News · Profile.
- **Locales** `ru`/`en`/`uz`/`tr`/`fa`/`zh` (ru primary) via i18next — keep all six in sync; `fa` is RTL.
- Forms use react-hook-form + zod. Wizard state lives in zustand, not URL/router state.
- Separate eslint/tsconfig from `dashboard/` — this is a plain Vite app, not Next.
