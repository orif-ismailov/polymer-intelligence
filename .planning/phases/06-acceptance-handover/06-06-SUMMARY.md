---
phase: 06-acceptance-handover
plan: 06
subsystem: docs
tags: [acceptance, handover, deployment-guide, admin-guide, russian, tz-6.1, certbot, webhook, userbot, secrets-matrix]

# Dependency graph
requires:
  - phase: 06-acceptance-handover
    provides: "06-01 uv.lock + reproducible CI (752→761 green); 06-02 restore drill (4s vs ≤2h) + runbook; 06-03 telegram_channel close test; 06-05 full-stack make smoke + source-failure isolation"
  - phase: 04-dashboard-source-constructor
    provides: "04-ACCEPTANCE.md structure; add-source wizard + enable-gate; alert-rule predicates"
  - phase: 03-client-circuit
    provides: "test_request_sla.py (§6.1.1 ≤10s / ≤30s proxies)"
  - phase: 02-ingest-core-uzex
    provides: "test_uzex_accuracy.py (§6.1.2 ≥95% on 55-position sample); pg_backup.sh + backup README"
  - phase: 05-telegram-monitoring-ai
    provides: "test_telegram_accuracy.py -m gate (§6.1.3 recall≥0.80/precision≥0.85); needs_review<0.5; per-source 7-day token budget; userbot/session.py"
provides:
  - "Consolidated Phase-1 acceptance sign-off spine (06-ACCEPTANCE.md) — one row per TZ §6.1.1–§6.1.6 with GREEN automated evidence, deploy-time drill, blocked-on customer input, sign-off line + single Deploy-Day Checklist superseding 02/03/05-UAT"
  - "First-run deployment guide (docs/deployment-guide.md, English) — placeholder secrets matrix, certbot TLS, first-run + make smoke, auto-registered webhook, userbot session, backup cron"
  - "Russian operator admin guide (docs/admin-guide-ru.md) — add-source (site + channel), alert rules, needs_review, token budget — satisfies TZ §9 «инструкция администратора»"
affects: [HANDOVER, 06-07-capstone, deploy-day-acceptance, customer-sign-off]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Acceptance spine: per-§6.1.x row = verbatim criterion → GREEN automated evidence (named test/harness/drill + measured result) → deploy-time drill → blocked-on customer input → sign-off"
    - "Consolidation pattern: a single Deploy-Day Checklist supersedes the per-phase deferred-UAT lists (02/03/05-UAT) rather than carrying parallel lists"
    - "Docs-as-evidence: every 'passing' claim is backed by a committed artifact produced this phase; customer-gated items are marked blocked-on, never claimed passed"

key-files:
  created:
    - .planning/phases/06-acceptance-handover/06-ACCEPTANCE.md
    - docs/deployment-guide.md
    - docs/admin-guide-ru.md
  modified: []

key-decisions:
  - "Webhook setup documented as AUTO-REGISTERED on api startup (telegram.bot.setup_webhook when PUBLIC_WEBAPP_URL set) — not a manual curl setWebhook — because that is the actual code path (app/main.py lifespan). Deviation from the plan's 'register the webhook URL' manual wording."
  - "Userbot session generation documented via the one-time interactive StringSession login in userbot/session.py (the docstring snippet, matching deploy/.env.example `python userbot/session.py`), not `python -m userbot.session` — userbot/session.py has no __main__ block; it exposes build_client() + the documented interactive flow. Deviation from the plan's `python -m userbot.session` wording."
  - "§6.1.2 marked 'no customer input required for the committed-sample gate' (test_uzex_accuracy.py passes ≥0.95 on the committed 55-position sample now), with an OPTIONAL customer UZEX export re-run — rather than blocking it on customer input. Accuracy over plan's optimistic blocked-on framing."
  - "§6.1.3 evidence carefully scoped: the gate harness + thresholds are GREEN on the committed EXAMPLE fixture (key-free); the real 100-message sample + trader sign-off is the customer-gated deploy-day step. Did not claim §6.1.3 passes on real data."
  - "userbot package lives at repo-root ./userbot (not backend/userbot); deployment guide + RU guide reference it accordingly."

patterns-established:
  - "Pattern: acceptance row carries a 'Blocked on (customer input)' line + a matrix mapping locally-proven-now vs deploy-day-blocked, so the customer sees exactly which §6.1.x are green and which await their inputs"
  - "Pattern: deployment guide ends by pointing at the acceptance Deploy-Day Checklist (one stand-up → one acceptance run)"

requirements-completed: []

# Metrics
duration: ~5 min
completed: 2026-06-22
---

# Phase 6 Plan 06: Acceptance & Handover Docs Summary

**Three handover docs grounded in this phase's executable proofs: a consolidated 06-ACCEPTANCE.md mapping each TZ §6.1.1–§6.1.6 criterion to its GREEN automated evidence (request-SLA proxies, UZEX ≥95% on 55 positions, the channel recall/precision gate, source-failure isolation via `make smoke`, the 4s-vs-2h restore drill, the telegram_channel close test) + a single Deploy-Day Checklist superseding 02/03/05-UAT; an English first-run deployment guide (placeholder secrets matrix, certbot TLS, auto-registered webhook, userbot session, backup cron); and a Russian operator admin guide (add-source, alert rules, needs_review, token budget).**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-22T10:29:52Z
- **Completed:** 2026-06-22T10:34:39Z
- **Tasks:** 3
- **Files modified:** 3 (all created)

## Accomplishments

- **`06-ACCEPTANCE.md`** — the customer-facing Phase-1 sign-off spine. One section per TZ §6.1.1–§6.1.6, each with: the verbatim Russian criterion + English gloss; the **specific GREEN automated evidence** already produced (named test/harness/drill + the concrete measured result); the deploy-time live drill steps; a **"Blocked on (customer input)"** line naming the exact gating input; and a dated **sign-off** line. A single **Deploy-Day Checklist** consolidates and **supersedes** the deferred deploy-time UAT items from `02-UAT.md`, `03-UAT.md`, and `05-UAT.md`. A closing matrix maps locally-proven-now vs deploy-day-blocked. §6.1.6 telegram slice is marked **CLOSED locally** (citing 06-03), retiring the Phase-4 SC#5 cross-phase caveat, with only live-account ingestion remaining.
- **`docs/deployment-guide.md`** (English) — stands the production stack up from scratch: prerequisites (OS, domain/DNS, ports 80/443 only); a **placeholder** env/secrets matrix (`VAR | Description | Source | Example`) with an explicit `.env`-outside-repo + rotation note; certbot TLS (with the real-domain swap for the `example.com` placeholder in `nginx.conf`); first-run `docker compose -f deploy/docker-compose.yml up -d` with the api entrypoint migrate+seed chain, `/health`, and `make smoke`; the **auto-registered** aiogram webhook; the userbot one-time StringSession setup; and the backup cron (referencing `deploy/backup/README.md` and linking the restore runbook rather than duplicating it).
- **`docs/admin-guide-ru.md`** (Russian) — task-oriented operator guide with 5 sections: add site source (`html_table`/`rss`) with the ≤10-row test preview and the **enable-gate** («источник с непройденным тестом включить нельзя», 422); add `telegram_channel` (same wizard, enable-gate, signals appear once userbot runs); the alert-rule builder (predicates `product_id`/`volume_gte`/`urgency_in`/`source_kind`/`lead_score_gte`, per-rule `chat_id` channels, dedupe, 25 msg/s); the `needs_review` queue (confidence < 0.5); and per-source 7-day token-budget monitoring (`token_spend_7d`, 500K daily UTC reset, budget-exhausted admin alert). Satisfies the TZ §9 «инструкция администратора» deliverable.

## §6.1.1–§6.1.6 status matrix (evidenced-as-passing now vs deploy-day blocked)

| TZ § | Criterion | Automated evidence (GREEN now) | Deploy-day: blocked on |
|------|-----------|--------------------------------|------------------------|
| §6.1.1 | request ≤10 s / status notify ≤30 s | `test_request_sla.py` (4 tests: readback <10s, notify enqueue ≤30s, no long sleep) — **proxy** | live wall-clock: real `BOT_TOKEN` + public HTTPS `PUBLIC_WEBAPP_URL` |
| §6.1.2 | UZEX ≥95% / ≥50 sample | `test_uzex_accuracy.py` asserts ≥0.95 on a committed **55-position** sample — **GREEN** | *none for committed gate* (optional customer UZEX export re-run) |
| §6.1.3 | channel recall ≥80% / precision ≥85% / 100-msg | `test_telegram_accuracy.py -m gate` asserts recall≥0.80 / precision≥0.85 on the committed **example** fixture (key-free) — gate GREEN | customer **100-message control sample** + `synonyms.json` + trader sign-off + live `ANTHROPIC_API_KEY` |
| §6.1.4 | source isolation + alert ≤30 min | `test_source_failure_alert.py` + `make smoke` (06-05) **ran LIVE**: sibling isolated, exactly one `source_failure` alert | live source-failure event on the production VPS |
| §6.1.5 | restore ≤2 h on clean server | `test_restore_local.sh` (06-02) **ran LIVE**: 4 s vs 7200 s budget; runbook validated | rerun on the real customer VPS (hardware timing) |
| §6.1.6 | admin add site + channel; failed-test cannot enable | `test_telegram_channel_close.py` (06-03, slice **CLOSED**: enable-gate 422 → message → signal → v_live_feed) + `test_source_wizard.py` (website e2e) | live userbot account/session + live channel (ingestion only) |

**Evidenced-as-passing now (local/CI/procedure level):** §6.1.2 (committed gate), §6.1.4 (isolation + single alert, ran live in `make smoke`), §6.1.5 (restore procedure, ran live at 4s), §6.1.6 (telegram slice closed + website e2e + enable-gate). **Proxy-only now, true SLA pending live infra:** §6.1.1. **Gate machinery green on example data, real-data sign-off customer-gated:** §6.1.3.

## Three docs produced

1. `.planning/phases/06-acceptance-handover/06-ACCEPTANCE.md` — consolidated sign-off spine (D-01).
2. `docs/deployment-guide.md` — first-run deployment guide (D-05.2, English).
3. `docs/admin-guide-ru.md` — operator admin guide (D-05.3, Russian).

## Task Commits

1. **Task 1: Author 06-ACCEPTANCE.md** — `c5ade0d` (docs)
2. **Task 2: Author docs/deployment-guide.md** — `207c60f` (docs)
3. **Task 3: Author docs/admin-guide-ru.md** — `76b8343` (docs)

## Files Created/Modified

- `.planning/phases/06-acceptance-handover/06-ACCEPTANCE.md` (created) — 6 §-rows + Deploy-Day Checklist + matrix.
- `docs/deployment-guide.md` (created) — 8 sections, placeholder secrets matrix, certbot, webhook, userbot, backup.
- `docs/admin-guide-ru.md` (created) — 5 Russian operator sections.

## Decisions Made

See `key-decisions` frontmatter. The load-bearing ones: webhook is documented as auto-registered on api startup (the real code path), not a manual `curl`; userbot session via the interactive StringSession flow in `userbot/session.py`; §6.1.2 committed-sample gate marked green-now (not blocked-on); §6.1.3 evidence scoped precisely to "gate green on example fixture, real-data sign-off customer-gated".

## Deviations from Plan

### Adjustments for accuracy (per the plan's own deviations directive — prefer truth over optimistic wording)

**1. [Rule 1 - Bug/accuracy] Webhook registration is automatic, not a manual `curl setWebhook` step**
- **Found during:** Task 2 (deployment guide)
- **Issue:** The plan task wording ("register the webhook URL at the public HTTPS endpoint") implies a manual registration call. The actual code (`backend/app/main.py` lifespan → `telegram.bot.setup_webhook()` when `PUBLIC_WEBAPP_URL` is set) auto-registers on api startup.
- **Fix:** Documented the real flow: set `BOT_TOKEN`/`WEBHOOK_SECRET`/`PUBLIC_WEBAPP_URL`, registration happens on startup, confirm via the `lifespan.telegram_webhook_registered` log line. Kept the WEBHOOK_SECRET double-check (path + header) and HTTPS-only guidance (T-06-17).
- **Files modified:** docs/deployment-guide.md
- **Verification:** Matches `app/main.py` lines 71–79 and `telegram/bot.py setup_webhook()`.
- **Committed in:** 207c60f

**2. [Rule 1 - Bug/accuracy] Userbot session entrypoint is `userbot/session.py` interactive login, not `python -m userbot.session`**
- **Found during:** Task 2 (deployment guide)
- **Issue:** The plan said generate `TG_SESSION_STRING` via `python -m userbot.session`. `userbot/session.py` (at repo-root `./userbot`, not `backend/userbot`) exposes `build_client()` and documents a one-time interactive `StringSession` snippet in its docstring; it has no `__main__` block, so `python -m userbot.session` would not run a generator. `deploy/.env.example` itself points at `python userbot/session.py` (interactive).
- **Fix:** Documented the one-time interactive StringSession login flow (the exact snippet from `userbot/session.py`) and the my.telegram.org prerequisites.
- **Files modified:** docs/deployment-guide.md, docs/admin-guide-ru.md
- **Verification:** Matches `userbot/session.py` docstring + `deploy/.env.example` line 34.
- **Committed in:** 207c60f

**3. [Rule 1 - accuracy] §6.1.2 marked not-blocked-on-customer-input for the committed gate**
- **Found during:** Task 1 (acceptance doc)
- **Issue:** The plan's blocked-on framing could imply §6.1.2 awaits customer input. `test_uzex_accuracy.py` already passes ≥0.95 on a committed 55-position sample (≥50 required) — the criterion is met at the gate level now.
- **Fix:** Marked §6.1.2 "Blocked on: none for the committed-sample gate" with an optional customer-export re-run, rather than a hard customer block.
- **Files modified:** .planning/phases/06-acceptance-handover/06-ACCEPTANCE.md
- **Verification:** `test_uzex_accuracy.py` asserts ≥0.95; fixture has 55 positions (confirmed via `json.load` count).
- **Committed in:** c5ade0d

---

**Total deviations:** 3 (all accuracy adjustments, per the plan's deviations directive — no fabricated passing criteria; customer-gated items kept explicitly blocked-on).
**Impact on plan:** Docs-only; no backend code changed; nothing regressed. The three adjustments make the docs match the real code path and real evidence instead of the plan's optimistic wording.

## Issues Encountered

None. All cited evidence artifacts (`test_request_sla.py`, `test_uzex_accuracy.py`, `test_telegram_accuracy.py`, `test_source_failure_alert.py`, `test_restore_local.sh`, `test_telegram_channel_close.py`, `test_source_wizard.py`, `deploy/.env.example`, `deploy/backup/README.md`, `deploy/nginx/nginx.conf`, `userbot/session.py`) were read/confirmed on disk before being cited.

## Known Stubs

None — all three docs cite real, committed artifacts and measured results from this phase. No placeholder data flows to a rendered surface; the "placeholder" values in the deployment guide secrets matrix are intentional (security requirement T-06-16 — no real secrets in docs).

## Threat Flags

None — docs-only plan, no new network/auth/file/schema surface introduced. The threat-model dispositions (T-06-16 no-secrets-in-docs, T-06-17 webhook HTTPS+secret, T-06-18 no-overstated-evidence) are all satisfied: secret scans returned NO SECRETS on all three files; webhook guidance mandates HTTPS + WEBHOOK_SECRET; every §6.1.x "passing" claim cites a named artifact and customer-gated items are marked blocked-on (no false sign-off).

## User Setup Required

None for this plan (docs-only). The docs themselves enumerate the customer-side deploy-day inputs (BOT_TOKEN, public HTTPS, userbot account/session, 100-message sample, real VPS) as blocked-on rows in the acceptance Deploy-Day Checklist.

## Next Phase Readiness

- The three §9 handover docs are ready for the 06-07 capstone / `HANDOVER.md` index to reference.
- 06-ACCEPTANCE.md is the single customer-facing acceptance spine; the Deploy-Day Checklist is the authoritative acceptance run (run `/gsd-verify-work 6` after the live drills).
- No blockers introduced.

## Self-Check: PASSED

- `.planning/phases/06-acceptance-handover/06-ACCEPTANCE.md` — FOUND on disk.
- `docs/deployment-guide.md` — FOUND on disk.
- `docs/admin-guide-ru.md` — FOUND on disk.
- Commits `c5ade0d`, `207c60f`, `76b8343` — all FOUND in git log.
- All three task `<acceptance_criteria>` re-run green (6 §-rows + Blocked on + Deploy-Day Checklist; certbot/webhook/userbot/backup tokens + no secrets; 5 Russian sections + enable-gate + no secrets).
- Secret scans on all three docs: NO SECRETS.

---
*Phase: 06-acceptance-handover*
*Completed: 2026-06-22*
