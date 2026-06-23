# Handover Index — Polymer Intelligence

**Milestone:** Phase 1 (Client circuit + ingest + dashboard + Telegram-channel monitoring)
**Date:** 2026-06-22
**Audience:** the customer/operator taking ownership of the system.
**Repository:** `git@github.com:orif-ismailov/polymer-intelligence.git`

This file is the single entry point for everything handed over under **TZ §9
«Передаваемые артефакты»** (source code, docker-compose, DB migrations, deployment +
restore documentation, prompt/extraction-schema descriptions, admin guide). Each row of the
Deliverables table below links the **actual repository path** of the artifact. Nothing here
contains real secrets — every credential in the linked docs is a placeholder; the real `.env`
lives one level above the repo root and is never committed.

---

## §9 Deliverables

| # | Artifact (TZ §9) | Location | Description |
|---|------------------|----------|-------------|
| 1 | Source code (repository) | This repo — `backend/` (FastAPI + ingest + userbot), `dashboard/` (Next.js dashboard), `webapp/` (Telegram Web App) | Full codebase. Origin: `git@github.com:orif-ismailov/polymer-intelligence.git`. |
| 2 | Production docker-compose | [`deploy/docker-compose.yml`](./deploy/docker-compose.yml) | The full production container set (Postgres, Redis, API, web, ingest worker, Telethon userbot, backup sidecar). Stood up and smoke-verified in 06-04/06-05. |
| 3 | DB migrations | [`backend/alembic/`](./backend/alembic/) (versions in [`backend/alembic/versions/`](./backend/alembic/versions/)) | Alembic migration chain `0001`→`0004` (initial schema, synonyms + classification queue, Phase-5 AI extraction, budget/index fix). Run via `alembic upgrade head`. |
| 4 | Deployment guide | [`docs/deployment-guide.md`](./docs/deployment-guide.md) | Bare-VPS → healthy-stack first-run procedure + the required-secrets matrix. References the restore runbook rather than duplicating it. |
| 5 | Backup / restore runbook | [`docs/runbook-backup-restore.md`](./docs/runbook-backup-restore.md) | ≤ 2-hour restore procedure (TZ §6.1.5), 14-daily / 8-weekly retention (REQ-nfr-reliability). Proven locally by [`tests/restore/test_restore_local.sh`](./tests/restore/test_restore_local.sh) (06-02). |
| 6 | Admin guide (RU) | [`docs/admin-guide-ru.md`](./docs/admin-guide-ru.md) | Russian operator manual: adding sources (website + Telegram channel), the alert-rule builder, the `needs_review` queue, and token-budget monitoring — no developer required. |
| 7 | Prompt + extraction-schema descriptions | Prompt: [`backend/parsing/prompts/extract_v1.md`](./backend/parsing/prompts/extract_v1.md) — Schema: [`docs/extraction-schema.json`](./docs/extraction-schema.json) | The immutable Phase-5 LLM extraction system prompt (`v1`, cache-threshold-tuned for Claude Haiku 4.5) and the published JSON signal/extraction schema the prompt emits against. |
| 8 | Acceptance sign-off | [`.planning/phases/06-acceptance-handover/06-ACCEPTANCE.md`](./.planning/phases/06-acceptance-handover/06-ACCEPTANCE.md) | TZ §6.1.1–§6.1.6 acceptance spine: per-criterion automated evidence (GREEN now) + the consolidated deploy-day live-drill checklist (blocked only on customer-provided real credentials/VPS). |

---

## How to verify the system

All commands run from the repository root unless noted.

### Restore drill (TZ §6.1.5, ≤ 2 h restore target)

```bash
bash tests/restore/test_restore_local.sh
```

Spins a throwaway Postgres, loads a dump, and asserts the schema/data restore end-to-end —
the local proof behind the runbook (see [`docs/runbook-backup-restore.md`](./docs/runbook-backup-restore.md)).

### Full-stack smoke (D-02)

```bash
make smoke
# → bash tests/smoke/test_smoke_full_stack.sh
```

Brings the production `deploy/docker-compose.yml` up with synthetic data and **placeholder**
env, then asserts every service reports healthy. This is the same compose handed over in row 2.

### Telegram-channel slice (TZ §6.1.6, key-free)

```bash
cd backend && python -m pytest tests/test_telegram_channel_close.py -q
```

Exercises the closed channel loop without any live credentials: wizard add → enable-gate
returns **422** until a Test passes → a fixture MTProto message flows through
`parse_telegram_item` → the resulting signal appears in `v_live_feed`. This is the test that
**retired the long-standing SC#5 cross-phase caveat** (see §9 row 8 / `06-ACCEPTANCE.md` and
ROADMAP SC#5).

### Backend regression suite & gates

```bash
cd backend && python -m pytest -q          # full suite
cd backend && ruff check . && mypy .       # lint + type gates
```

---

## What remains for deploy day

The locally-provable slices of TZ §6 are GREEN now. The remaining items are **live drills**
blocked only on customer-provided inputs (a real Telegram bot token + public HTTPS endpoint, a
live userbot account/session, the customer's 100-message control sample, and the production
VPS). They are enumerated as a single **Deploy-Day Checklist** at the bottom of
[`06-ACCEPTANCE.md`](./.planning/phases/06-acceptance-handover/06-ACCEPTANCE.md), each with a
sign-off line for the trader to date and initial at acceptance.

---

## Ongoing support (TZ §8)

Per TZ §8, sustained operation (collector repair when sources change, userbot-account rotation,
prompt tuning, channel additions, monitoring) is a **separate monthly support agreement** — not
part of this one-time handover. Without support, collectors degrade over time for reasons
outside the developer's control.
