# Phase 3: Client Circuit - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the client-facing loop: a client opens the Telegram Web App, authenticates via
Telegram initData (first login creates a `clients` row), completes a 4-step purchase-request
wizard (with optional file attachments), gets a confirmation number `REQ-YYYY-MM-DD-NNNNN`,
sees "Мои заявки" with statuses + history, and receives an aiogram bot push on every status
change. RU/UZ throughout.

In scope: Web App request wizard + my-requests + i18n, the `/webapp/*` backend API,
initData auth, request_service (number + status machine + history + notify), file upload to
MinIO, and the aiogram client bot (webhook). Out of scope: the internal dashboard /
live-feed / purchase-requests admin screens (Phase 4), AI extraction (Phase 5), the userbot /
Telegram channel monitoring (Phase 5), published reports in the Web App (future milestone).
</domain>

<decisions>
## Implementation Decisions

### Request Wizard (4-step submission)
- **D-01:** Wizard state is **client-only** (zustand) until submit — no server-side resumable drafts. On submit: `POST /webapp/requests` creates the request and returns its id + number; any step-3/4 files then attach to that request id. (Resumable server drafts considered and deferred — see Deferred.)
- **D-02:** Minimum required to submit = **product + grade/type + volume**. Everything else (target price, Incoterms/country/port/date/validity, comment, files) is optional — low-friction lead capture.
- **D-03:** **Per-step blocking validation** — the client cannot advance until the current step is valid. Use `zod` + `react-hook-form` (already in `webapp/package.json`). Inline errors per field.

### Client Bot (aiogram 3, webhook in the api container)
- **D-04:** Bot messages render in the **client's RU/UZ preference** — defaulted from Telegram `language_code` on first login, toggleable in the Web App, persisted on the `clients` row. Message templates live in `telegram/templates/{ru,uz}/` (dev-spec §4.1).
- **D-05:** Status-change push is **detailed**: `Заявка REQ-YYYY-MM-DD-NNNNN → {client-facing status}` plus an inline deep-link button that opens that request in the Web App. Fired by a Celery task on status change; ≤30 s SLA (TZ §6.1.1).
- **D-06:** `/start` = greeting (RU/UZ by `language_code`) + a **persistent Web App launch (menu) button** + an inline Web App button; creates/finds the `clients` row.

### File Upload
- **D-07:** Upload path = **backend-proxied multipart → MinIO** (aligns dev-spec §4.2; this overrides an earlier presigned-direct-to-MinIO inclination after the dev-spec conflict was surfaced). The Web App POSTs files to the backend, which validates and streams them into MinIO. `storage_path` already exists in the `request_files` schema.
- **D-08:** Limits enforced **client-side (UX) AND authoritatively in the backend**: **magic-byte MIME validation** (not file extension), ≤10 MB per file, ≤5 files. Reject before persisting.
- **D-09:** `telegram_file_id` is the **fallback only for files sent directly to the bot**; Web App uploads always go to MinIO.

### Client Status Visibility
- **D-10:** The client sees a **simplified status map** (7 internal `RequestStatus` → client-facing set), RU/UZ labeled:
  `new → Отправлена`, `viewed + in_progress → На рассмотрении`, `offer_sent → Предложение получено`, `matched → Подобрано`, `closed → Закрыта`, `cancelled → Отменена`. Internal distinctions (e.g. viewed vs in_progress) are hidden from the client.
- **D-11:** The request detail view shows the **full status-history timeline** with **Asia/Tashkent** timestamps (from `request_status_history`).

### Claude's Discretion
- **Request number generation:** `REQ-YYYY-MM-DD-NNNNN` via a per-date DB sequence (dev-spec §3 `request_service`) — concurrency-safe counter; implementation detail.
- **initData auth (locked, not re-discussed):** header `X-Telegram-Init-Data`, HMAC signature verification on every request, TTL 24 h (dev-spec §3, REQ-webapp-auth).
- **Status machine transitions (dev-spec §3):** `new→viewed→in_progress→{offer_sent, closed, cancelled}`; `matched` from `in_progress`/`offer_sent`. Validate transitions server-side; write `request_status_history` + `audit_log`.
- **Performance budget tactics** (≤3 s first paint on 3G, ≤300 KB gzip bundle, request appears ≤10 s) — research/planner to handle (code-split, lazy routes, Vite build tuning).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/ROADMAP.md` — Phase 3: Client Circuit (goal + the 4 success criteria)
- `.planning/REQUIREMENTS.md` — REQ-webapp-auth, REQ-request-wizard, REQ-my-requests, REQ-webapp-i18n, REQ-bot-clients, REQ-nfr-performance (with TZ acceptance SLAs)

### Build spec (how we build)
- `docs/polymer-intelligence-dev-spec.md` §3 — `request_service` (REQ-…-NNNNN number gen via date sequence, status machine, history, client-notify), Web App auth (`X-Telegram-Init-Data` HMAC per request, TTL 24 h), and the `/webapp/*` API surface (`POST /webapp/requests`, `GET /webapp/requests`, `GET /webapp/requests/{id}`, `POST /webapp/requests/{id}/files`, `GET·PATCH /webapp/me`)
- `docs/polymer-intelligence-dev-spec.md` §4.1 — aiogram 3 bot via **webhook** `POST /telegram/webhook/{secret}` (no separate bot container — runs in api); `/start` greeting + Web App button; status-change templates in `telegram/templates/{ru,uz}/`
- `docs/polymer-intelligence-dev-spec.md` §4.2 — file upload decision: **backend → MinIO**, magic-byte MIME validation, `telegram_file_id` fallback for bot-sent files (the canonical resolution for D-07)

### Client TZ (priority over dev-spec on any conflict)
- `docs/polymer-intelligence-tz.md` §6.1.1 — SLAs: request appears in dashboard ≤10 s; status-change notification ≤30 s

### Schema (locked, DDL v1.1)
- `docs/polymer-intelligence-db-architecture.md` — `clients`, `requests`, `request_files`, `request_status_history`

### Mockups (REQ-request-wizard "per mockups")
- `docs/polymer-intelligence-ui-mockups.md` — 4-step wizard + "Мои заявки" layouts (also `docs/photo_2026-06-13 17.57.0{6,8,10}.jpeg`)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `webapp/` scaffold — stack already chosen in `package.json`: React 18, `@telegram-apps/sdk`, `react-i18next` + `i18next`, `react-hook-form`, `zod`, `zustand`, Vite. `src/App.tsx` already uses `var(--tg-theme-*)` CSS variables (no hardcoded colors). The wizard, my-requests, and i18n all build on this.
- `backend/app/models/requests.py` — `Client`, `Request`, `RequestFile` (has `storage_path` + `telegram_file_id`), `RequestStatusHistory` ORM models already defined (schema locked). `Request.number` unique, `Request.status` PgEnum.
- `backend/app/models/enums.py` — `RequestStatus` enum (new/viewed/in_progress/offer_sent/matched/closed/cancelled) drives D-10's client map.
- `backend/app/core/config.py` — `S3_ENDPOINT`/S3 settings already stubbed (Phase 1 deferred the actual MinIO client to this phase).
- `backend/app/tasks/celery_app.py` + `schedule.py` (02-01) — Celery with a `notify` queue already exists; the ≤30 s status-change push is a `notify`-queue task.

### Established Patterns
- **TZ:** UTC in DB, Asia/Tashkent on display (`DEC-tz-handling`) — apply to the history timeline (D-11) and push timestamps.
- **Audit:** Phase 1 `audit_log` write pattern (`db.flush()`, caller commits) — reuse for request status transitions.
- **No hardcoded colors:** Web App = tg-theme vars; SQLAlchemy 2 typed models; idempotent ON CONFLICT writes.

### Integration Points
- aiogram bot runs as a FastAPI **webhook** inside the `api` container (dev-spec §1 — "bot не нужен отдельно (вебхук в api)"), not a separate service and not long-polling.
- Add **MinIO** to `deploy/docker-compose.dev.yml`; construct the S3 client in the backend (first real use of the `S3_*` config).
- Status change → enqueue a Celery `notify` task that sends the bot push (≤30 s).
</code_context>

<specifics>
## Specific Ideas

- Bot is **webhook-based** (`POST /telegram/webhook/{secret}`) in the api container — explicitly not polling, not a separate container.
- Client-facing status labels are a deliberate simplification of the 7 internal statuses, shown in RU/UZ (D-10).
- File attachment sequencing under the client-only wizard: **submit creates the request first**, then files POST to `/webapp/requests/{id}/files` — no server draft needed.
</specifics>

<deferred>
## Deferred Ideas

- **Server-side resumable wizard drafts** (resume a half-filled request across sessions/devices) — considered, deferred in favor of client-only state for the MVP (D-01). Revisit if clients report losing progress.
- **Published reports in the Web App** (`GET /webapp/reports`) — dev-spec marks this Phase 2 / future-milestone; out of scope here.
- Otherwise discussion stayed within phase scope.
</deferred>

---

*Phase: 3-client-circuit*
*Context gathered: 2026-06-16*
