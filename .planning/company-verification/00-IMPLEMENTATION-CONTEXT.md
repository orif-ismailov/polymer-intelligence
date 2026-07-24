# Implementation context — READ FIRST (applies to R1, R2, R3)

This file is the shared contract for any agent/developer implementing the Company Verification & Portal plans (R1-PLAN.md, R2-PLAN.md, R3-PLAN.md). Read it fully before touching code. The design rationale lives in ARCHITECTURE.md (same directory) — consult it for the *why*; the R-plans are the *what/how*.

## Repo orientation

Monorepo `polymer-intelligence` (see root `CLAUDE.md` and per-component `CLAUDE.md` files — **read the component guide before working in its directory**):
- `backend/` — FastAPI + Celery + SQLAlchemy 2, Python 3.12, **uv**-managed. All backend commands run from `backend/` via `uv`.
- `dashboard/` — Next.js 16 App Router, internal staff dashboard, next-intl locales ru/uz/tr/fa/zh.
- `webapp/` — Vite React Telegram Mini App. **FROZEN: do not modify anything in `webapp/` in any release.**
- `portal/` — NEW (created in R1): Vite + React + TypeScript + Tailwind + shadcn/ui + TanStack Query + react-router-dom + zustand, Feature-Sliced Design. Client cabinet.
- `telegram/` — aiogram bot package at repo root (mounted read-only into containers).
- `deploy/` — docker-compose (prod + dev), nginx, `.env.example` = the authoritative env contract.

Work on the `dev` branch. The dev stack on the server auto-pulls `dev` every few minutes.

## Hard conventions (violating any of these = broken build or broken prod)

1. **Test-driven development, per task (not per wave):** every task in every wave (R1/R2/R3) writes or extends its tests *first/alongside* the code, and **the relevant tests are run and must pass after that task** — testing is never deferred to the end of a wave. Then, **the full test suite before every commit:** `cd backend && pytest tests/ -q` must be green (not a subset). Frontends: `npm run lint` (`--max-warnings 0`) + `npm run typecheck` per touched app; Playwright e2e where a plan task specifies it. Testing infrastructure available: an ephemeral Postgres (`docker run --rm postgres:16`) for real `alembic upgrade head` / `downgrade -1` / re-upgrade drills; the mocked-DB `TestClient` suite (`backend/tests/conftest.py`) for API/unit; and the guarded real-DB integration path (a `test_polymer` DB against a local Postgres). Each wave's **Acceptance** block is the minimum test set for that wave — treat it as the checklist, not the ceiling.
2. **No AI co-author footers** in commits or PR bodies. Conventional commits: `feat(verification): …`, `fix(portal): …`.
3. **New SQLAlchemy model modules** must be imported in `backend/app/models/__init__.py` in FK-dependency order, or alembic's `env.py` won't see them.
4. **Domain enums** are `(str, Enum)` (NOT `StrEnum`) in `backend/app/models/enums.py`; values match Postgres ENUM DDL verbatim. Every new enum or enum value = alembic migration + edit to the DB architecture doc under `docs/` in the same commit.
5. **New Celery task modules** must be added to `_TASK_MODULES` in `backend/app/tasks/celery_app.py` (autodiscover is a no-op). Queue set must match compose: currently `-Q ingest,parse,notify,default` at `deploy/docker-compose.yml:207` and `deploy/docker-compose.dev.yml:131` (R1 extends both with `,verify`), contract documented in `deploy/CLAUDE.md`.
6. **Integration adapters self-register at import time**; the importing process is the only one that sees them. Import new adapter modules in BOTH `backend/app/main.py` AND the worker-side task module that uses them.
7. **Secrets have no defaults** in `backend/app/core/config.py` (`Settings`; import the module-level `settings`, never construct `Settings()`). Adding a required secret = update `deploy/.env.example` + CI placeholder envs in `.github/workflows/ci.yml` + note for prod `../.env` **in the same commit**, or every environment breaks at startup.
8. **mypy is strict** for `app/services/` and `app/schemas/` (CI-gated): `mypy app/services --ignore-missing-imports` and same for `app/schemas`. Business logic goes in `app/services/`, typed.
9. **Domain exceptions without `Error` suffix** (`InvalidInitData`, `BudgetExceeded` style; ruff N818 disabled).
10. **Time:** store UTC, display `Asia/Tashkent` (`app/core/time.py`, dashboard `lib/tz.ts`).
11. **Migrations:** `backend/alembic/versions/`, sequential numbering (0016 is current head before R1). `alembic upgrade head` and `downgrade -1` must both work.
12. **Pinned tooling:** `uv sync --frozen --extra dev`; do not bump `ruff`/`mypy`/`fastapi` pins.
13. **Audit:** every state-changing decision writes `audit_service.write_audit(db, staff_user_id, action, entity, entity_id, details)` in the same transaction (flush-only; caller commits). Telegram/system actors: `staff_user_id=None` + actor info in `details`.
14. **Notify pattern:** Telegram-sending Celery tasks live in `backend/app/tasks/notify.py`, queue `notify`, enqueue fail-soft (`.apply_async(..., queue="notify", retry=False)` inside try/except), tasks never raise (return error dicts).
15. **Storage:** file uploads via `backend/app/services/storage_service.py` — size check then magic-byte MIME detection (never trust extension), traversal-safe keys, `put_object` to `settings.S3_BUCKET`, DB row flushed not committed.
16. **Runtime settings** (operator-tunable, no deploy): add `SettingSpec` to `_SPECS` in `backend/app/services/settings_service.py`; they appear in the dashboard admin panel automatically.
17. **i18n:** keep locale files complete per surface — bot/telegram: ru/uz/tr; dashboard: ru/uz/tr/fa/zh; portal (new): ru/uz/en at launch. Missing keys fail review.
18. **CI:** `.github/workflows/ci.yml`. R1 adds a `portal` job (npm ci → lint → tsc → build) mirroring the `webapp` job. Keep all existing jobs green.

## Key design invariants (from ARCHITECTURE.md — do not "simplify" them away)

- **Identity:** person = `user_accounts` (phone E.164, passwordless OTP). Company membership = `company_members(user_account_id)`. Telegram identities (`clients`/`sellers`) are a separate, frozen world; `user_accounts.telegram_user_id` is a dormant nullable column, no bridge logic in R1–R3.
- **Bounded contexts stay separate:** company registry / verification / compliance / trust / integration gateway / document vault are separate modules; cross-context effects go through the `domain_events` outbox (written in the same DB transaction as the state change). No direct cross-context model imports.
- **Evidence is immutable:** external payloads (registry snapshots, signed challenges, PKCS#7) are append-only rows; never mutate.
- **State machines are data:** transition tables like `request_service.VALID_TRANSITIONS` (`backend/app/services/request_service.py:114`) — copy that pattern; illegal transitions raise domain exceptions.
- **Concurrency:** human decisions = optimistic (`UPDATE … WHERE status='…'`, rowcount 0 → already handled, idempotent no-op); machine evaluators = `SELECT … FOR UPDATE`; invariants = DB constraints (partial unique indexes, CHECKs), not app-level ifs.
- **Degradation:** external-provider failure makes a check `unavailable` (retry/waive), never blocks the whole pipeline. A dead provider must not starve other queues — provider calls run on the `verify` queue.
- **No enforcement flips in code:** publish gates etc. are runtime settings defaulting to off; flipping them is an operator action, not a deploy.

## Existing code to mirror (best available templates)

| Need | Copy the pattern from |
|---|---|
| Moderation state machine + dual actioning (dashboard + TG inline) | `backend/app/services/offer_service.py` (`moderate_offer`, `moderate_offer_via_telegram`), `backend/app/api/moderation.py`, `telegram/handlers/moderation.py` (callback `offer:<action>:<id>`, group-admin authz, idempotency) |
| Status transition table + history journal | `backend/app/services/request_service.py` (`VALID_TRANSITIONS`, `transition_status`, `request_status_history`) |
| File upload service | `storage_service.upload_offer_file` |
| Staff JWT + RBAC deps | `backend/app/api/deps.py` (`get_current_staff_user`, `require_role`, `require_admin`, `require_analyst_or_admin`) |
| Session cookies | `app/services/auth_service.py` (`set_client_session_cookie`) |
| Runtime settings | `settings_service.py` `_SPECS` |
| Group notification card with inline keyboard | `app/tasks/notify.py` `send_offer_to_group` |
| Localized client DM | `app/tasks/notify.py` `send_status_change_notification` |
| Wizard frontend (multi-step + zustand) | `webapp/src` request wizard (`/request/step/1..4` + confirm) — read-only reference, do not modify webapp |
| Admin queue UI | `dashboard/app/[locale]/(dashboard)/moderation` |

## Environment / secrets added across R1–R3 (cumulative)

| Var | Release | Secret? | Notes |
|---|---|---|---|
| `VERIFICATION_ENC_KEY` | R1 | yes | Fernet key, ≥32 urlsafe-b64 chars; encrypts bank accounts (R1) and PINFL (R3) |
| `SMS_PROVIDER` | R1 | no | `console` (default, dev/CI) or `eskiz` |
| `ESKIZ_EMAIL`, `ESKIZ_PASSWORD` | R1 | yes | required only when `SMS_PROVIDER=eskiz` (model validator) |
| `OTP_TTL_SECONDS=300`, `OTP_RESEND_COOLDOWN_SECONDS=60`, `OTP_MAX_SENDS_PER_DAY=5`, `OTP_MAX_VERIFY_ATTEMPTS=5`, `PORTAL_SESSION_TTL_DAYS=30` | R1 | no | tunables with defaults |
| `VERIFICATION_NOTIFY_CHAT_ID` | R1 | no | optional; falls back to `REQUEST_NOTIFY_CHAT_ID` |
| `EIMZO_SERVER_URL` | R3 | no | sidecar base URL, e.g. `http://eimzo-server:8080` |
| `EIMZO_CHALLENGE_TTL_SECONDS=300` | R3 | no | |

## Definition of done (every release)

1. All waves merged to `dev`, full CI green.
2. `alembic upgrade head` idempotent on a copy of prod schema.
3. The release's demo script (defined in each plan) passes on the dev stack.
4. Docs updated: relevant `CLAUDE.md` files, DB doc, `deploy/.env.example`, RU admin guide where staff-facing behavior changed.
5. No modifications under `webapp/`.
