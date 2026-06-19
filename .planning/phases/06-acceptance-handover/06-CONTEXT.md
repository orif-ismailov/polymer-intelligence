# Phase 6: Acceptance & Handover - Context

**Gathered:** 2026-06-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Cross-cutting **verification and handover** of the completed Client-Phase-1 system — no
net-new product features. Phase 6 proves every TZ §6.1.1–6.1.6 acceptance criterion, proves
the DB restore procedure, and produces the §9 handover deliverables.

**In scope:**
- A single consolidated `06-ACCEPTANCE.md` mapping each TZ §6.1.1–6.1.6 item → exact procedure
  → current automated-proxy evidence → the specific customer input it is blocked on → sign-off
  line. This **consolidates and supersedes** the per-phase deferred deploy-time UAT items
  (02-UAT, 03-UAT, 05-UAT) into one deploy-day checklist.
- A **local full-stack docker-compose smoke** run against synthetic/fixture data (compose up →
  migrate+seed → `/health` → submit a synthetic request → see it in `v_live_feed` → force a
  fake-source failure → observe per-source isolation + `source_failure` alert). Doubles as
  validation of the deployment guide.
- A **fixture/mock-driven local close of §6.1.6's telegram_channel slice** (deferred from Phase 4):
  wizard adds a `telegram_channel` source → Test → enable-gate (failed test cannot enable) → a
  fixture MTProto message flows through `parse_telegram_item` → signal lands in `v_live_feed`.
- A **local restore test (§6.1.5)** executed now (pg_dump → fresh PG16 container → restore via the
  runbook → verify → record wall-clock timing).
- **Handover deliverables (§9):** production `docker-compose.yml` (full container set), a deployment
  guide, an admin guide (RU), and a `HANDOVER.md` index.
- **Handover hygiene (folded todo):** commit a `uv.lock` (or pinned requirements), fix the 2 stale
  route-introspection tests, make CI reproducible.

**Out of scope (stays deploy-day / customer-gated, documented in 06-ACCEPTANCE.md, NOT executed here):**
- Live drills requiring customer inputs: real `BOT_TOKEN` + public HTTPS (§6.1.1 live wall-clock),
  3-strike live source-failure on real sources (§6.1.4 on the VPS), real userbot account/API_ID/
  API_HASH/session + a live channel (§6.1.6 live ingestion), the customer 100-message control
  sample + synonyms + trader sign-off (§6.1.3 real-data 80/85 gate), restore rerun on the actual
  customer VPS (§6.1.5 hardware timing).
- Any Phase-2 / Future-Milestone work (international loop, reports, counterparty linking).
- No new product screens or endpoints — verification + docs only.
</domain>

<decisions>
## Implementation Decisions

### Acceptance protocol form
- **D-01:** Produce **one consolidated `06-ACCEPTANCE.md`** as the single Phase-1 sign-off
  artifact. For each TZ §6.1.1–6.1.6 item it records: the exact verification procedure, the
  current automated-proxy evidence already green (UZEX 100% / 55 positions; AI eval 100/100 on
  fixtures; SLA proxies 4/4; feed ≤500 ms @ ~1M rows; RBAC matrix), the specific customer input
  the live drill is blocked on, and a sign-off line. It **consolidates the deferred deploy-time
  UAT items from 02-UAT / 03-UAT / 05-UAT** into one deploy-day checklist (no parallel per-phase
  lists). (Doc-only-without-smoke was considered and rejected — see D-02.)
- **D-02:** **Also run a local full-stack docker-compose smoke** against synthetic/fixture data:
  compose up → migrate+seed → `/health` → submit a synthetic request → see it in `v_live_feed` →
  force a deliberately-failing fake source → observe per-source isolation + `source_failure` alert.
  Purpose is twofold: a fresh end-to-end confidence check before handover, and live validation
  that the deployment guide (D-07) actually stands the system up. It does NOT replace the
  customer-gated live drills (those stay in 06-ACCEPTANCE.md).

### Channel source-constructor acceptance (§6.1.6)
- **D-03:** **Close the telegram_channel slice locally, fixture/mock-driven, with no real account.**
  Prove the full chain deterministically: wizard adds a `telegram_channel` source → Test → the
  enable-gate refuses to enable a source with no passing test (`is_enabled = true ⇒
  last_test_ok_at IS NOT NULL`) → a fixture MTProto message is fed through `parse_telegram_item` →
  the extracted signal appears in `v_live_feed`. Mirrors how Phase 5 closed the eval gate
  key-free on committed fixtures. The real-account live ingestion remains the deploy-day drill
  (05-UAT item 1). This finally retires the SC#5 cross-phase caveat carried since Phase 4.

### Restore test (§6.1.5)
- **D-04:** **Run the restore test locally now and record the wall-clock timing.** Execute
  pg_dump → fresh PG16 container → restore strictly via `docs/runbook-backup-restore.md` → verify
  table/row counts + schema (`v_live_feed`, ENUMs) → record elapsed time against the ≤2 h budget.
  Self-contained (no customer input). A fresh container counts as a "clean server" for proving the
  *procedure*; the deploy-day rerun on the real VPS confirms hardware timing only. Any runbook gaps
  surfaced here are fixed in the same phase (the runbook is a §9 deliverable).

### Handover deliverables (§9)
- **D-05:** Author **all four** net-new artifacts (existing docs that are reused, not rewritten:
  `docs/runbook-backup-restore.md`, `docs/extraction-schema.json`, the three spec docs):
  1. **Production `docker-compose.yml`** — full container set (api, worker, beat, userbot,
     dashboard, postgres, redis, nginx). Only `deploy/docker-compose.dev.yml` exists today; a
     production compose is required for any real deploy and for the D-02 smoke.
  2. **Deployment guide** — env/secrets matrix, TLS via certbot, first-run migrate+seed, aiogram
     bot webhook + userbot session setup, backup cron. (Restore is already covered by the runbook.)
  3. **Admin guide** — non-developer operator instructions: add-source wizard (site + channel),
     alert-rule builder, needs_review queue, token-budget monitoring. Satisfies §9 "инструкция
     администратора".
  4. **`HANDOVER.md` index** — single entry point linking every §9 deliverable (repo, compose,
     deployment + restore docs, prompt/extraction-schema descriptions, admin guide).
- **D-06:** **Language split** — the **Admin guide is written in Russian** (its audience is the
  customer's Russian-speaking operator; the Web App + TZ are RU/UZ). The **deployment guide,
  production compose, and `HANDOVER.md` index stay in English** (technical/ops audience, consistent
  with the existing English `docs/` dev-spec + db-architecture).

### Folded Todos
- **D-07 (folded todo — "Backend dependency reproducibility + 2 stale route-introspection tests"):**
  As handover hygiene, **commit a `uv.lock`** (or exact-pinned requirements) so the customer can
  rebuild the backend deterministically, **fix/refresh the 2 stale route-introspection tests** that
  break under FastAPI/Starlette drift, and confirm CI is green and reproducible. A clean, green,
  reproducible build is part of "the system is documented and handed over." (Tracked in
  `.planning/todos/pending/backend-dep-reproducibility-and-stale-route-tests.md`.)

### Claude's Discretion (for research/planning)
- Synthetic/fixture data shape for the D-02 smoke and the D-03 channel close (reuse existing test
  fixtures where possible).
- Exact structure/section ordering of `06-ACCEPTANCE.md`, the deployment guide, and the admin guide.
- Whether the D-02 smoke is wired as a scripted make/CI target vs. a documented manual sequence.
- Choice of pin mechanism for D-07 (`uv.lock` vs. pinned `requirements.txt`) consistent with the
  existing `pyproject.toml` toolchain.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase definition & scope
- `.planning/ROADMAP.md` — Phase 6: Acceptance & Handover (goal + the 4 success criteria; note the
  SC#5 telegram cross-phase caveat now retired by D-03)
- `.planning/REQUIREMENTS.md` — Phase 6 is cross-cutting verification of all 24 v1 requirements
  (no net-new requirements); see the Traceability table for the per-phase mapping

### Acceptance criteria (authoritative)
- `docs/polymer-intelligence-tz.md` §6 (lines 173–187) — Phase-1 acceptance criteria 1–6
  (§6.1.1 request ≤10 s / notify ≤30 s; §6.1.2 UZEX ≥95% on ≥50; §6.1.3 channel recall ≥80% /
  precision ≥85% on 100-msg sample; §6.1.4 source isolation + alert ≤30 min; §6.1.5 restore ≤2 h;
  §6.1.6 admin adds site + channel, failed-test can't enable)
- `docs/polymer-intelligence-tz.md` §9 (lines 219–221) — handover artifacts list
- `docs/polymer-intelligence-tz.md` §7 (lines 190–196) — risk allocation (userbot account/layout/
  AI-quality thresholds borne by customer; relevant when wording sign-off conditions)

### Deferred drills this phase consolidates
- `.planning/phases/02-ingest-core-uzex/02-UAT.md` — deferred live UZEX/source-failure/restore drills
- `.planning/phases/03-client-circuit/03-UAT.md` — deferred live client-circuit drill (SC#1–SC#5)
- `.planning/phases/05-telegram-monitoring-ai/05-UAT.md` — deferred live userbot ingestion drill +
  real-data §6.1.3 80/85 gate
- `.planning/phases/04-dashboard-source-constructor/04-ACCEPTANCE.md` — Phase-4 acceptance + the SC#5
  telegram cross-phase caveat retired here
- `.planning/phases/05-telegram-monitoring-ai/05-VERIFICATION.md` — 15/15 automated must-haves verified

### Existing handover assets (reuse, do not rewrite)
- `docs/runbook-backup-restore.md` — restore procedure (validated + refined by D-04; a §9 deliverable)
- `docs/extraction-schema.json` — published extraction schema (referenced by HANDOVER index)
- `docs/polymer-intelligence-dev-spec.md` — container topology, API surface, deploy notes
  (CI = ruff/mypy/eslint+tsc → tests → image build; deploy via ssh script)
- `docs/polymer-intelligence-db-architecture.md` — locked PG16 DDL v1.1 (restore-verify target:
  all tables/ENUMs + `v_live_feed`)

### Deploy/ops scaffolding to extend
- `deploy/docker-compose.dev.yml` — dev compose; production `docker-compose.yml` (D-05.1) extends it
- `deploy/Dockerfile.backend`, `deploy/Dockerfile.dashboard` — images for the production compose
- `deploy/nginx/nginx.conf`, `deploy/nginx/nginx.dev.conf` — reverse proxy + TLS-ready config
- `deploy/backup/pg_backup.sh`, `deploy/backup/README.md` — backup script referenced by the restore test
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Automated acceptance proxies already green** — reference them as evidence in 06-ACCEPTANCE.md
  rather than re-deriving: UZEX accuracy harness (100% / 55 positions, TZ §6.1.2), AI eval golden-set
  gate (`tests/parsing/test_telegram_accuracy.py`, 100/100 on fixtures, TZ §6.1.3), SLA proxies
  (`test_request_sla.py` 4/4, §6.1.1), feed perf test (≤500 ms @ ~1M rows), dashboard RBAC matrix test.
- **`parse_telegram_item` orchestrator** (Phase 5, 05-04) — drives the D-03 fixture channel close
  (budget gate → extract/fallback → one `parse_runs` row → `signals.ai` stamp → confidence<0.5
  needs_review). Feed a fixture raw_item through it.
- **SourceAdapter registry + enable-gate** (Phase 2/4) — `telegram_channel` adapter (`test()`/`fetch()`,
  Phase 5 live) + the server-side `is_enabled = true ⇒ last_test_ok_at IS NOT NULL` invariant power
  the D-03 wizard→Test→enable-gate proof.
- **`run_source_fetch_isolated` + 3-strike `source_failure` dedupe** (Phase 2, 02-06) — drives the
  D-02 forced-fake-source-failure isolation+alert smoke without touching real sources.
- **`deploy/` scaffolding** (compose.dev, Dockerfiles, nginx, pg_backup.sh) — the base the D-05
  production compose + deployment guide build on.

### Established Patterns
- **Fixture/key-free verification** — Phase 5 proved the eval gate deterministically on committed
  fixtures; apply the same approach to the D-02 smoke and D-03 channel close (no real credentials).
- **Deferred-then-consolidate UAT** — every prior phase deferred its live drill to deploy time with
  user sign-off; Phase 6 is the agreed convergence point (D-01).
- **Source-enable DB invariant** — must be re-demonstrated for `telegram_channel` (D-03).

### Integration Points
- The D-02 smoke exercises the real wiring end-to-end: webapp request → request_service →
  `v_live_feed`; fake source → `run_source_fetch_isolated` → `source_failure` alert.
- The production compose (D-05.1) must define the **userbot** service (separate long-lived process,
  not a Celery task) and the **aiogram webhook** on the api service (no separate bot container) per
  the locked runtime topology.
</code_context>

<specifics>
## Specific Ideas

- `06-ACCEPTANCE.md` is the customer-facing sign-off spine: one row per §6.1.x item, columns for
  procedure / automated evidence / blocked-on customer input / sign-off — readable by the customer,
  not just the team.
- The D-02 smoke should also serve as the deployment-guide smoke test, so "stand it up" and "prove
  it works locally" are the same sequence.
- The Admin guide (RU) should be screenshot-light, task-oriented ("how to add a channel", "how to
  build an alert rule", "what needs_review means", "where to watch token budget").
- Retire the long-standing SC#5 telegram cross-phase caveat (carried in 04-CONTEXT.md / ROADMAP SC#5)
  explicitly once D-03 passes.
</specifics>

<deferred>
## Deferred Ideas

- **Live customer-gated drills** (real `BOT_TOKEN` + public HTTPS §6.1.1; real userbot account/session
  + live channel §6.1.6 ingestion; customer 100-message control sample + synonyms + trader sign-off
  §6.1.3; live source-failure on the VPS §6.1.4; restore rerun on the customer VPS §6.1.5) — NOT
  deferred to a future phase; they are documented in `06-ACCEPTANCE.md` as deploy-day steps and run
  via `/gsd-verify-work 6` (or `5` for the AI gate) when the customer inputs land. This is product
  decision, not a gap.
- Phase-2 / Future-Milestone items (international feed, webapp news, reports approval, counterparty
  linking, intraday channel publishing) remain registered in REQUIREMENTS.md and out of this milestone.

</deferred>

---

*Phase: 6-acceptance-handover*
*Context gathered: 2026-06-19*
