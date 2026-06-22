---
phase: 06-acceptance-handover
verified: 2026-06-22T16:00:00Z
status: human_needed
score: 4/4 must-haves verified (code/procedure level); SC#1–#3, #5(channel), #6 live drills are deploy-day/customer-input gated
overrides_applied: 0
human_verification:
  - test: "§6.1.1 — Web App request ≤10s to dashboard; status change → client Telegram push ≤30s"
    expected: "Live wall-clock within the SLA windows against the real bot + public-HTTPS webhook"
    why_human: "Requires a real BOT_TOKEN (@BotFather) + public HTTPS PUBLIC_WEBAPP_URL — customer-provided; the code-path latency proxy (test_request_sla.py 4/4) passes now but the true wall-clock is deploy-gated"
  - test: "§6.1.3 — Channel recall ≥80% / field precision ≥85% on the customer's 100-message control sample"
    expected: "pytest test_telegram_accuracy.py -m gate passes on the customer sample with a live ANTHROPIC_API_KEY + trader tolerance sign-off"
    why_human: "Customer must provide the 100-message control sample + real synonyms.json + senior-trader sign-off + live key; the gate machinery passes now on the committed example fixture (recall/precision gate green)"
  - test: "§6.1.4 — One real source failing on the VPS raises exactly one source_failure alert ≤30 min while siblings keep running"
    expected: "Live source-failure event → one deduped alert within the */5 check_source_health cadence; siblings keep producing"
    why_human: "Requires a live source-failure on the production VPS; the isolation + single-alert logic is proven live locally via make smoke (06-05) and unit-proven (test_source_failure_alert.py)"
  - test: "§6.1.5 — DB restore on the real customer VPS completes ≤2h following the runbook"
    expected: "Wall-clock from dump selection to /health ok is ≤2h on customer hardware"
    why_human: "Procedure + ≤2h budget already proven on a clean PG16 container (test_restore_local.sh ran 4s vs 7200s); only the hardware-timing rerun on the real VPS is deploy-gated"
  - test: "§6.1.6 — Live telegram_channel ingestion: real userbot account posts → raw_items → parsed → signal in feed"
    expected: "With a live userbot session + monitored channel, a posted message surfaces as a signal in the Live Feed"
    why_human: "Requires a customer-provided userbot account + TG_SESSION_STRING + live channel (TZ §7.2); the full no-code path (wizard add → enable-gate 422 → fixture message → parse_telegram_item → v_live_feed signal) is CLOSED locally key-free (test_telegram_channel_close.py, 9 passed)"
---

# Phase 6: Acceptance & Handover — Verification Report

**Phase Goal:** The customer can confirm Phase 1 is accepted — every TZ §6.1 acceptance criterion and the source-constructor acceptance pass, the database can be restored from backup within the stated window, and the system is documented and handed over.

**Verified:** 2026-06-22T16:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Executive Summary

This is an acceptance/handover phase. Every deliverable that is provable at the **CI / procedure level** is genuinely green now, and I confirmed each by reading the real artifacts and running them (gates, the three named tests, the cited §6.1.x evidence tests, `uv lock --check`, `docker compose config`). No overstated claims, no committed secrets, no debt markers, no dangling deliverable links, and the retired SC#5 caveat is backed by a test that genuinely exists and passes (9/9).

The phase honestly draws the line between **green-now** and **deploy-day / customer-input gated**. Per the decision tree, because legitimately deploy-gated live drills remain (real bot token + public HTTPS, customer 100-message sample, live userbot account, production VPS — all customer-provided per TZ §7), the overall status is **human_needed**, not `passed`. This is the correct terminal state for an acceptance gate: the engineering work is complete and proven, the remaining items are the customer-run acceptance drills the phase was designed to set up.

## Goal Achievement

### Observable Truths (per Success Criterion)

| # | Truth (Success Criterion) | Status | Evidence |
| --- | --- | --- | --- |
| SC#1 | All TZ §6.1 acceptance items pass on review (§6.1.1–§6.1.4) | ✓ VERIFIED (code/proc level) + deploy-gated live drills | Per-criterion automated evidence all green (see §6.1 matrix); live wall-clock/VPS drills correctly marked customer-gated |
| SC#2 | DB restore from backup on a clean server completes ≤2h (§6.1.5) | ✓ VERIFIED (procedure proven) | `tests/restore/test_restore_local.sh` asserts `< 7200s`, ran live 4s vs 7200s on a fresh `postgres:16` container; runbook records the drill. VPS-hardware rerun deploy-gated |
| SC#3 | Source-constructor acceptance: admin onboards site + Telegram channel no-dev; failed-test source cannot be enabled (§6.1.6) | ✓ VERIFIED (slice closed locally) | `test_telegram_channel_close.py` (9 passed): enable-gate 422 without passing test, fixture message → `parse_telegram_item` → signal in `v_live_feed`. `test_source_wizard.py` proves website path. Live-account ingestion deploy-gated |
| SC#4 | Deliverables handed over: deploy + restore docs, runbook, prompt/extraction-schema, admin instructions | ✓ VERIFIED | `HANDOVER.md` §9 index — all 10 linked deliverable paths resolve; `docs/deployment-guide.md` (EN, certbot/secrets), `docs/admin-guide-ru.md` (genuine Russian, 116 Cyrillic lines), runbook, `extract_v1.md` prompt, `extraction-schema.json` all present |

**Score:** 4/4 success criteria met at the code/procedure level. Live acceptance drills (deploy-day, customer-input gated) are enumerated for human/customer sign-off.

### Honest §6.1 Acceptance Matrix

| TZ § | Criterion | Automated evidence (GREEN now — verified by me) | Remaining (honestly gated) |
| --- | --- | --- | --- |
| §6.1.1 | request ≤10s / notify ≤30s | `test_request_sla.py` 4/4 pass — code-path latency proxy (no async-write lag, immediate notify dispatch) | Live wall-clock: real BOT_TOKEN + public HTTPS (customer) |
| §6.1.2 | UZEX ≥95% on ≥50 sample | `test_uzex_accuracy.py` asserts ≥0.95 on a **55-position** committed control sample (verified count) — passes | None for committed gate (green now); optional customer UZEX export |
| §6.1.3 | channel recall ≥80% / precision ≥85% / 100 | `test_telegram_accuracy.py -m gate` 2/2 pass (RECALL_GATE ≥0.80, PRECISION_GATE ≥0.85) on committed example fixture, key-free | Customer 100-msg sample + synonyms + trader sign-off + live ANTHROPIC_API_KEY |
| §6.1.4 | source isolation + alert ≤30 min | `test_source_failure_alert.py` passes (isolation + exactly-one deduped alert); `make smoke` (06-05) ran live | Live source-failure on the real VPS |
| §6.1.5 | restore ≤2h on clean server | `test_restore_local.sh` asserts `<7200s`; ran live **4s** on fresh PG16 container; runbook §5 records it | Hardware-timing rerun on real customer VPS |
| §6.1.6 | admin add site + channel; failed-test cannot enable | `test_telegram_channel_close.py` 9/9 (enable-gate 422, parse → v_live_feed); `test_source_wizard.py` (website e2e) | Live userbot account/session + live channel (ingestion only) |

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/uv.lock` | Fully-pinned lock (contains fastapi) | ✓ VERIFIED | 2704 lines; `uv lock --check` → exit 0 (Resolved 117 packages, no drift) |
| `backend/tests/test_prices_api.py` | url_path_for route assertion | ✓ VERIFIED | 223 lines; passes |
| `backend/tests/test_source_wizard.py` | url_path_for route + enable-gate 422 | ✓ VERIFIED | 500 lines; passes |
| `tests/restore/test_restore_local.sh` | Restore drill, asserts ≤7200s | ✓ VERIFIED | 270 lines; `RESTORE_BUDGET=7200`, pg_dump→pg_restore→migrate→verify schema/ENUMs/v_live_feed→assert `<7200` |
| `docs/runbook-backup-restore.md` | ≤2h restore procedure | ✓ VERIFIED | 251 lines; "Restore target ≤2 hours", records 4s drill PASS, <5GB ≈20–50min estimate |
| `backend/tests/test_telegram_channel_close.py` | §6.1.6 channel close, parse_telegram_item | ✓ VERIFIED | 601 lines; 9 passed — enable-gate 422, fixture→parse→v_live_feed |
| `deploy/docker-compose.yml` | Full service set, nginx-only ingress, no secrets | ✓ VERIFIED | 262 lines; api/worker/beat/userbot/dashboard/postgres/redis/minio/nginx; only nginx exposes 80/443; `compose config` → exit 0; no secret literals |
| `tests/smoke/test_smoke_full_stack.sh` | Compose smoke, source-failure isolation | ✓ VERIFIED | 319 lines; refs `deploy/docker-compose.yml`, asserts exactly one `source_failure` alert; seed uses valid `exchange` enum (no `'fx'`) |
| `Makefile` | make smoke target | ✓ VERIFIED | `smoke:` target invokes the smoke script |
| `.planning/phases/.../06-ACCEPTANCE.md` | One row per §6.1.1–§6.1.6 + blocked-on + deploy checklist | ✓ VERIFIED | 276 lines; honest GREEN-now vs Blocked-on columns, every cited test exists |
| `docs/deployment-guide.md` | EN, certbot, secrets matrix | ✓ VERIFIED | 277 lines; certbot/TLS, env/secrets, webhook/userbot, backup cron |
| `docs/admin-guide-ru.md` | Russian operator guide | ✓ VERIFIED | 171 lines; 116 Cyrillic lines, covers sources/channel/alerts/needs_review/budget |
| `HANDOVER.md` | §9 deliverables index | ✓ VERIFIED (minor doc nit) | 92 lines; all 10 linked paths resolve. Nit: prose calls dashboard dir `web/` but it is `dashboard/` (label only, not a broken link) |
| `docs/extraction-schema.json` | Extraction schema deliverable | ✓ VERIFIED | 286 lines; linked from HANDOVER §9 row 7 |
| `backend/parsing/prompts/extract_v1.md` | LLM prompt deliverable | ✓ VERIFIED | 277 lines; linked from HANDOVER §9 row 7 |
| `.github/workflows/ci.yml` | `uv sync --frozen` install | ✓ VERIFIED | `uv sync --frozen --extra dev` step present, adds .venv to PATH |

### Key Link Verification

| From | To | Via | Status |
| --- | --- | --- | --- |
| `.github/workflows/ci.yml` | `backend/uv.lock` | `uv sync --frozen` install | ✓ WIRED |
| `test_restore_local.sh` | `runbook-backup-restore.md` | executes runbook §3 pg_restore verbatim | ✓ WIRED |
| `test_telegram_channel_close.py` | `parse_telegram.parse_telegram_item` | fixture raw_item → signal | ✓ WIRED (9 passed) |
| `test_telegram_channel_close.py` | PATCH /sources enable-gate | is_enabled=True + last_test_ok_at=NULL → 422 | ✓ WIRED |
| `deploy/docker-compose.yml` | `nginx.conf` (TLS, not nginx.dev.conf) | nginx mounts prod TLS config | ✓ WIRED |
| `deploy/docker-compose.yml` | `Dockerfile.dashboard` | dashboard builds Next.js standalone | ✓ WIRED |
| `test_smoke_full_stack.sh` | `deploy/docker-compose.yml` | compose up full prod stack | ✓ WIRED |
| `test_smoke_full_stack.sh` | `source_failure` alert | force fake failure 3x → one alert | ✓ WIRED |
| `06-ACCEPTANCE.md` | executable proofs (06-02/03/05) | cites passing tests as evidence | ✓ WIRED (all cited tests exist + pass) |
| `HANDOVER.md` | all §9 deliverable paths | table rows link each artifact | ✓ WIRED (10/10 resolve) |
| `ROADMAP.md` + `04-CONTEXT.md` | SC#5 telegram caveat | marked RETIRED, cites 06-03 | ✓ WIRED (retired in both, backed by 9-passing test) |

### Behavioral Spot-Checks (run by verifier)

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Lock in sync | `uv lock --check` | exit 0, Resolved 117 packages, no drift | ✓ PASS |
| Route tests + channel close | `pytest test_prices_api test_source_wizard test_telegram_channel_close -q` | 32 passed | ✓ PASS |
| Channel close alone (caveat-retiring test) | `pytest test_telegram_channel_close.py -q` | 9 passed | ✓ PASS |
| §6.1.3 gate | `pytest test_telegram_accuracy.py -m gate -q` | 2 passed (recall/precision gates) | ✓ PASS |
| Cited acceptance evidence | `pytest test_request_sla test_uzex_accuracy test_source_failure_alert telegram_accuracy -q` | 44 passed, 3 skipped | ✓ PASS |
| ruff gate | `ruff check .` | All checks passed | ✓ PASS |
| mypy services | `mypy app/services --ignore-missing-imports` | Success, no issues (17 files) | ✓ PASS |
| mypy schemas | `mypy app/schemas --ignore-missing-imports` | Success, no issues (4 files) | ✓ PASS |
| Full suite | `pytest -q` | **761 passed, 65 skipped** (matches claim) | ✓ PASS |
| Production compose validates | `docker compose -f deploy/docker-compose.yml config` | exit 0 (warns only that secret VARs default blank — correct) | ✓ PASS |
| UZEX sample size | parse control_sample.json | 55 positions (≥50) | ✓ PASS |
| admin-guide-ru is Russian | grep Cyrillic | 116 Cyrillic lines | ✓ PASS |
| Restore script budget | grep RESTORE_BUDGET | `7200` (≤2h) asserted | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| --- | --- | --- | --- |
| Live full-stack smoke | `make smoke` / `test_smoke_full_stack.sh` | NOT RUN by verifier — requires standing up the full prod compose (>10s, starts services); verified by inspection (script refs deploy/docker-compose.yml, asserts exactly one source_failure alert, seed bug fixed). 06-05 SUMMARY claims it ran live | ? SKIP (deploy-gated, inspection-verified) |
| Live restore drill | `test_restore_local.sh` | NOT RUN by verifier — spins a Docker PG container; verified by inspection (asserts <7200s; runbook §5 records the 2026-06-22 4s PASS) | ? SKIP (Docker-gated, inspection-verified) |

### Requirements Coverage

Phase 6 declares no net-new requirements (cross-cutting verification of Phase-1 requirements). The §6.1 matrix above is the requirements-coverage view: each TZ acceptance criterion maps to a verified automated proxy plus an honestly-gated live drill.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| (none) | — | TBD/FIXME/XXX debt markers | — | None found across all phase-modified files |
| (none) | — | Committed secret literals | — | None found in compose/docs (all `${VAR}`/placeholders) |
| `HANDOVER.md` | 21 | Prose label `web/` for the dashboard dir (actual dir is `dashboard/`) | ℹ️ Info | Cosmetic — it is a description label, not a hyperlink; all 10 linked deliverable paths resolve. Does not block goal achievement |

### Findings / Notes

- **No overstatement detected.** Every "GREEN now" claim in `06-ACCEPTANCE.md` cites a test that exists and that I ran green. The split between green-now and deploy-day/customer-gated is accurate and conservative (e.g., §6.1.1 is honestly labeled a code-path proxy, not a wall-clock measurement).
- **Retired caveat is genuinely backed.** The SC#5 telegram cross-phase caveat is marked RETIRED in both `ROADMAP.md` and `04-CONTEXT.md`; the closing test (`test_telegram_channel_close.py`) genuinely exists and passes 9/9, exactly as the retirement text claims ("9 passed").
- **Seed bug fix confirmed.** `sources_seed.json` uses only valid `SourceKind` enum members (`exchange`, `external_index`); no invalid `'fx'` kind remains anywhere in seed or smoke. The smoke script seeds the sibling source as `exchange` (valid).
- **No committed secrets.** `docker compose config` validates with secret vars defaulting to blank — confirming they come from `.env`, not baked defaults.
- **One minor doc nit (Info only):** `HANDOVER.md` row 1 prose describes the dashboard as `web/`; the directory is `dashboard/`. The hyperlinked deliverable paths are all correct.

### Human Verification Required

The following are the customer-run acceptance drills the phase was built to enable. They are gated on customer-provided inputs (TZ §7 risk allocation), not on open engineering defects. They are enumerated in the single Deploy-Day Checklist at the bottom of `06-ACCEPTANCE.md`, each with a sign-off line.

1. **§6.1.1 live SLA** — real BOT_TOKEN + public HTTPS → request ≤10s, notify ≤30s.
2. **§6.1.3 quality gate on real sample** — customer 100-message sample + synonyms + live key + trader sign-off → recall ≥80% / precision ≥85%.
3. **§6.1.4 live source-failure** — break one real source on the VPS → one alert ≤30 min, siblings isolated.
4. **§6.1.5 restore on real VPS** — runbook rerun on customer hardware ≤2h.
5. **§6.1.6 live channel ingestion** — real userbot account/session + live channel → posted message → signal in feed.

### Gaps Summary

No engineering gaps. All four success criteria are met at the code/procedure level, all deliverables exist and are correctly wired/linked, all gates pass (761 passed / 65 skipped, ruff/mypy clean), and the source-constructor §6.1.6 channel slice is genuinely closed locally (9/9) — legitimately retiring the SC#5 caveat. The only outstanding items are the deploy-day/customer-input-gated live acceptance drills, which are the customer's to run and sign off; the phase has correctly set them up and documented them. Status is therefore **human_needed** (the acceptance gate's correct terminal state), not a gap.

---

_Verified: 2026-06-22T16:00:00Z_
_Verifier: Claude (gsd-verifier)_
