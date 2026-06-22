# Phase 1 Acceptance — TZ §6.1.1–§6.1.6 Sign-off Spine

**Milestone:** Phase 1 (Client circuit + ingest + dashboard + channel monitoring)
**Criteria source:** `docs/polymer-intelligence-tz.md` §6 «Критерии приёмки» Фаза 1, items 1–6 (lines 176–181)
**Created:** 2026-06-22
**Status:** Pending deploy-time customer-gated verification — the locally-provable slices are GREEN now (cited below); the remaining live drills are blocked on customer-provided inputs (real bot token + public HTTPS, a live userbot account/session, the customer's 100-message control sample, and the production VPS) and are listed in the single **Deploy-Day Checklist** at the bottom.

---

## How to read this document

Each TZ §6.1.x row gives:

1. **Full criterion** — the verbatim TZ text (Russian) + an English gloss.
2. **Automated evidence (GREEN now)** — the specific committed test/harness/drill that proves the criterion at the CI / procedure level, with the concrete result already measured this phase.
3. **Deploy-Time Live Drill** — the numbered steps that confirm the criterion against real production infrastructure.
4. **Blocked on (customer input)** — the specific input each live drill awaits. If this column is empty the criterion is fully closed locally.
5. **Sign-off** — a line for the customer/trader to date and initial at acceptance.

This file **consolidates and supersedes** the per-phase deferred deploy-time UAT lists in
`02-UAT.md`, `03-UAT.md`, and `05-UAT.md` — do not run those separately; the single
[Deploy-Day Checklist](#deploy-day-checklist) below is the authoritative acceptance run.

> **Risk allocation (TZ §7).** Per the contract: the userbot account/session and the channel list are **customer-provided** (§7.2); AI-extraction quality thresholds are fixed at the §6 values and anything beyond is iterative support, not a defect (§7.4); customer is responsible for published-content sign-off (§7.5). The "Blocked on" entries below reflect that allocation — they are customer inputs, not open engineering defects.

---

## §6.1.1 — Request appears in dashboard ≤10 s; status notification ≤30 s

**Full criterion (TZ):** «Заявка, поданная через Web App, появляется в дашборде ≤10 сек; смена статуса доставляет клиенту уведомление ≤30 сек.»
**Gloss:** A request submitted via the Web App is queryable on the backend within 10 s; a status change delivers the client a notification within 30 s.

### Automated evidence (GREEN now)

```bash
cd backend && python -m pytest tests/test_request_sla.py -q
```

- **`backend/tests/test_request_sla.py`** — the §6.1.1 SLA proxy (4 tests, all green in the 761-test suite):
  - `test_request_readback_within_10s` — POST `/api/v1/webapp/requests` → GET `/api/v1/webapp/requests`; asserts the create→readback elapsed time **< 10.0 s** and that the returned `REQ-…` number is present in the list (proves the create path persists synchronously — no async-write lag).
  - `test_status_change_enqueues_notify_promptly` — `transition_status` enqueues the notify push on the `notify` queue with **no `countdown`/`eta`** (immediate dispatch ⇒ the ≤30 s budget is bounded by Celery delivery only).
  - `test_notify_task_no_long_sleep` — source-scans `app.tasks.notify` for any `time.sleep(>1s)` that could blow the ≤30 s budget; none present.
  - `test_sla_test_module_imports_cleanly` — CI collection guard.

These are CI-safe, DB-mocked **proxies**: they prove the code path has no structural latency, but the true wall-clock depends on the live bot + public HTTPS path.

### Deploy-Time Live Drill

1. Bring up the production stack (`docker compose -f deploy/docker-compose.yml up -d`) with a real `BOT_TOKEN`, `WEBHOOK_SECRET`, and public-HTTPS `PUBLIC_WEBAPP_URL` in `.env`.
2. Open the Telegram Web App, submit a purchase request.
3. Confirm the request appears in the dashboard `/requests` list **within 10 s**.
4. Change the request status in the dashboard; confirm the client receives the Telegram push notification **within 30 s** (with the localized status label + deep-link button).

**Pass criteria:** Steps 2–4 succeed within the stated SLA windows.

**Blocked on (customer input):** a real `BOT_TOKEN` (from @BotFather) + a public HTTPS endpoint for `PUBLIC_WEBAPP_URL` so Telegram can reach the webhook and deliver pushes. (This is the consolidation of `03-UAT.md` tests 1–3, all deferred at the 03-06 checkpoint pending real bot token + public HTTPS.)

**Sign-off:** ____________________  Date: __________

---

## §6.1.2 — UZEX polymer positions present with correct fields (≥95% on ≥50 sample)

**Full criterion (TZ):** «Полимерные позиции тестового торгового дня UZEX присутствуют в signals с корректными полями (проверка по контрольной выборке ≥50 позиций, точность ≥95%).»
**Gloss:** Polymer positions from a UZEX test trading day are present in `signals` with correct fields, verified on a control sample of ≥50 positions at ≥95% accuracy.

### Automated evidence (GREEN now)

```bash
cd backend && python -m pytest tests/test_uzex_accuracy.py -q
```

- **`backend/tests/test_uzex_accuracy.py`** — the §6.1.2 acceptance gate. Reads `tests/fixtures/uzex/control_sample.json` (**55 positions** committed — above the ≥50 requirement), runs each raw position through the real rule-based UZEX parse pipeline, computes field-level accuracy over the structural/numeric fields the parser controls, and **asserts accuracy ≥ 0.95**. Fixture-validity tests assert the sample exists, is valid JSON, has ≥50 positions, and every position carries `raw` + `expected` with the required fields.

This gate runs on a **committed control sample**; the customer may additionally supply their own UZEX test-day export to re-run the same harness at deploy time for a fully customer-owned sign-off.

### Deploy-Time Live Drill

1. On the live stack, run (or wait for the beat schedule to run) a real UZEX fetch for a test trading day.
2. Confirm polymer positions land in `signals` with correct `product`/`grade`/`volume`/`price`/`currency`/`section`/`kind`.
3. (Optional, customer-owned) Drop the customer's UZEX test-day control export into `tests/fixtures/uzex/control_sample.json` and re-run `pytest tests/test_uzex_accuracy.py`; confirm ≥95%.

**Pass criteria:** Positions present with correct fields; accuracy ≥95% on the (committed or customer) ≥50-position sample.

**Blocked on (customer input):** *None required for the committed-sample gate* (it is green now). Optional: a customer-supplied UZEX test-day export for a customer-owned re-run. (Consolidates the live-ingest portion of `02-UAT.md` test 1.)

**Sign-off:** ____________________  Date: __________

---

## §6.1.3 — Channel recall ≥80% / field precision ≥85% on the 100-message sample

**Full criterion (TZ):** «На контрольной выборке из 100 сообщений каналов (готовит заказчик): полнота обнаружения релевантных сигналов ≥80%, точность извлечения полей у обнаруженных ≥85%. Ошибки LLM-извлечения сверх этих порогов не являются дефектом.»
**Gloss:** On a 100-message channel control sample (prepared by the customer): relevant-signal recall ≥80%, field-extraction precision on detected signals ≥85%. LLM-extraction errors beyond these thresholds are not a defect.

### Automated evidence (GREEN now — on the committed example fixture)

```bash
cd backend && python -m pytest tests/parsing/test_telegram_accuracy.py -m gate -q
```

- **`backend/tests/parsing/test_telegram_accuracy.py`** — the §6.1.3 eval harness (from plan 05-05). It loads the golden control sample via `golden_loader`, computes **recall (D1)** and **aggregate field precision (D3–D9)** via `eval_metrics`, and the `-m gate` tests **assert `recall ≥ 0.80` (`RECALL_GATE`) and `precision ≥ 0.85` (`PRECISION_GATE`)** — these BLOCK CI. In CI the harness runs against the **committed example fixture** (key-free, no live Anthropic call), and passes; the harness is identical for the real customer sample.

The gate machinery is proven and wired; the **threshold sign-off on the real 100-message sample is the customer-gated step** (see Blocked on).

### Deploy-Time Live Drill (TZ §6.1.3)

1. Place the customer's **100-message control sample** at `GOLDEN_SET_PATH` (+ the real `synonyms.json`).
2. With a live `ANTHROPIC_API_KEY`, run the refresh path to generate frozen predictions for `prompt_version v1`.
3. Run `pytest tests/parsing/test_telegram_accuracy.py -m gate`; confirm recall ≥80% (D1) and per-field precision ≥85% (D3–D9).
4. A senior trader signs off the two §5.3 defaults (price ±0.5% tolerance; synonym-aware grade counts toward the gate).

**Pass criteria:** recall ≥80% and field precision ≥85% on the customer's 100-message sample, with trader sign-off on the tolerances.

**Blocked on (customer input):** the customer's **100-message control sample** + a real `synonyms.json` + senior-trader sign-off on the §5.3 tolerances, and a live `ANTHROPIC_API_KEY` to generate predictions. Per TZ §7.4, results within these thresholds are acceptance; anything beyond is iterative support, not a defect. (Consolidates `05-UAT.md` test 2.)

**Sign-off:** ____________________  Date: __________

---

## §6.1.4 — One source failing does not stop the others; failure alert ≤30 min

**Full criterion (TZ):** «Отключение одного источника не прерывает работу остальных; алерт о сбое приходит ≤30 мин.»
**Gloss:** One source failing does not interrupt the others; a failure alert arrives within 30 min.

### Automated evidence (GREEN now)

```bash
cd backend && python -m pytest tests/test_source_failure_alert.py -q
make smoke   # full-stack live proof (06-05)
```

- **`backend/tests/test_source_failure_alert.py`** — proves per-source isolation: `run_source_fetch_isolated` never re-raises, so a failing source's exception is caught and recorded while siblings keep running; after 3 consecutive failures `record_fetch_failure` → `raise_source_failure_alert` inserts **exactly one** `alerts` row with `kind='source_failure'`, deduped on `source_failure:{source_id}:{UTC-date}` via `ON CONFLICT (dedupe_key) DO NOTHING`.
- **`tests/smoke/test_smoke_full_stack.sh` (`make smoke`, plan 06-05)** — ran this against the **live production-compose stack**: forced a fake source's `fetch()` to raise 3×, asserted (a) the healthy sibling still recorded `last_success_at` with `consecutive_failures=0` (isolation) and (b) **exactly one** `source_failure` alert for the fake source. Live logs confirmed three `uzex_fetch.source_error` lines followed by one `source_health.alert_raised`. Printed `[smoke] PASSED`, exit 0, twice. The ≤30 min window is delivered operationally by the `*/5` `check_source_health` beat task.

### Deploy-Time Live Drill

1. On the live stack, point one real source at an unreachable URL (or disable its upstream).
2. Force/await 3 fetch cycles.
3. Confirm exactly one `source_failure` alert is raised (deduped per source per day) and that it lands **within 30 min** (the `*/5` `check_source_health` cadence).
4. Confirm sibling sources keep producing signals throughout (isolation), and that a subsequent success resets `consecutive_failures` to 0.

**Pass criteria:** sibling isolation holds; exactly one deduped `source_failure` alert within 30 min.

**Blocked on (customer input):** a live source-failure event on the production VPS (so the alert delivery path and the ≤30 min cadence are confirmed against the customer's real sources/channels). The isolation + single-alert logic is proven live locally (06-05). (Consolidates `02-UAT.md` test 2.)

**Sign-off:** ____________________  Date: __________

---

## §6.1.5 — DB restore from backup on a clean server ≤2 hours

**Full criterion (TZ):** «Восстановление БД из бэкапа на чистом сервере по документации — ≤2 часов.»
**Gloss:** Restoring the database from a backup onto a clean server, following the documentation, takes ≤2 hours.

### Automated evidence (GREEN now — restore drill ran LIVE)

```bash
bash tests/restore/test_restore_local.sh
```

- **`tests/restore/test_restore_local.sh` (plan 06-02)** — **ran LIVE end-to-end**: `pg_dump --format=custom` of the running DB → restore onto a **fresh disposable `postgres:16-alpine` container** (a clean server; distinct name/port `55432`/tmpfs — never the dev volume) via the runbook §3 commands → `alembic upgrade head` to revision `0004` → verify per-table row equality (signals 45 / raw_items 0 / sources 3 all match source) + the 14 locked ENUMs + `v_live_feed` (51 rows) → asserts elapsed **< 7200 s**. **Measured 4 s vs the ≤2 h (7200 s) budget — PASS.**
- **`docs/runbook-backup-restore.md`** — the §9 handover restore procedure, validated/refined by that live run (the three real procedural gaps it surfaced — superuser role `pi_user`, `pg_restore --jobs` needs a file not a pipe, and migration-vs-dump-revision image staleness — were fixed in the runbook). §5 records the 2026-06-22 drill (4 s, PASS) and the < 5 GB production estimate (≈20–50 min), comfortably inside the 2 h window.

### Deploy-Time Live Drill

1. On a **clean customer VPS** (or a fresh container), select a recent `.pgdump` per runbook §2.
2. Follow `docs/runbook-backup-restore.md` §3 (DROP/CREATE DB as `pi_user` → `pg_restore --jobs=4` from a file → `app.entrypoint` migrate → re-seed → restart).
3. Record the wall-clock from dump selection to `/health` ok; confirm **≤2 h**.
4. Run the §4 post-restore checklist (health `db: ok, redis: ok`; api/worker/beat Up; spot-check a recent signal).

**Pass criteria:** restore completes and the stack is healthy within ≤2 h on the customer hardware.

**Blocked on (customer input):** a rerun on the **real customer VPS** to confirm hardware timing (the procedure + the ≤2 h budget are already proven on a clean PG16 container). (Consolidates `02-UAT.md` test 3, the restore-doc walkthrough — now upgraded from a doc read to an executed drill.)

**Sign-off:** ____________________  Date: __________

---

## §6.1.6 — Admin adds a site + a Telegram channel with no developer; failed-test source cannot be enabled

**Full criterion (TZ):** «Администратор без участия разработчика добавляет через дашборд новый публичный сайт и новый Telegram-канал; сигналы из них появляются в ленте; источник с неуспешным тестом включить невозможно.»
**Gloss:** An admin, without a developer, adds a new public website and a new Telegram channel via the dashboard; their signals appear in the feed; a source whose test failed cannot be enabled.

### Automated evidence (GREEN now — telegram-channel slice CLOSED locally)

```bash
cd backend && python -m pytest tests/test_telegram_channel_close.py tests/test_source_wizard.py -q
```

- **`backend/tests/test_telegram_channel_close.py` (plan 06-03)** — closes the §6.1.6 **telegram_channel** slice locally and deterministically, key-free (no live MTProto/Anthropic). 9 tests prove: a wizard-saved `telegram_channel` source is pending (`is_enabled=False`, `last_test_ok_at=NULL`); **PATCH `is_enabled=True` while `last_test_ok_at=NULL` → 422** (the enable-gate, T-06-06); a passing Test stamps `last_test_ok_at` → enable → 200; non-admin create/enable → 403; a fixture channel message flows through `parse_telegram_item` (writing a `parse_runs` row before the signal — G5) into a real `Signal` carrying the channel `source_id` + extracted fields; and that signal maps cleanly through `app.api.feed._row_to_feed_item` to a validated `FeedItem` (the `v_live_feed` contract). Low-confidence (`<0.5`) → `needs_review=True` (G2 boundary preserved).
- **`backend/tests/test_source_wizard.py`** — proves the **website** path end-to-end at the API level (`html_table`/`rss`): the form auto-builds from the adapter's `config_schema`, `POST /{id}/test` returns a ≤10-row preview, and the enable-gate returns **422** without a passing test. The website onboarding is fully end-to-end from Phase 4.

> **§6.1.6 telegram-channel slice is CLOSED locally** (cite 06-03). This retires the Phase-4 "SC#5 cross-phase caveat" (which had marked "telegram-channel signals appear in feed" as a Phase-5/6 item): the full no-code path — wizard add → enable-gate → fixture message → `parse_telegram_item` → `v_live_feed`-shaped signal — is now proven deterministically. **Only live-account ingestion remains a deploy-day step.**

### Deploy-Time Live Drill (TZ §6.1.6)

**Website (already end-to-end in Phase 4):**
1. Log in as admin → `/sources` → Add Source → pick HTML Table / RSS.
2. Fill the auto-generated form; Run Test → confirm `ok:true` + ≤10 preview rows.
3. Enable → confirm `is_enabled=true`; trigger a fetch → confirm new signals appear in the Live Feed.

**Telegram channel (live-account ingestion is the remaining deploy-day step):**
4. With a real userbot account/session running (`TG_API_ID/HASH/SESSION_STRING` in `.env`, `docker compose up userbot`), add a `telegram_channel` source via the wizard; Run Test → enable.
5. Post a message in the live monitored channel; confirm a `raw_items` row appears, is parsed, and the resulting signal shows in the Live Feed.

**Enable-gate invariant:**
6. Find any source with `last_test_ok_at IS NULL`; attempt PATCH enable → confirm **422**.

**Pass criteria:** website end-to-end (steps 1–3); telegram live-account ingestion (steps 4–5); enable-gate 422 (step 6).

**Blocked on (customer input):** a **real userbot account + `TG_SESSION_STRING` + a live monitored channel** for the live-account ingestion (steps 4–5) — per TZ §7.2 the account is customer-provided. The enable-gate and the message→signal→feed contract are proven locally (06-03). (Consolidates `05-UAT.md` test 1, the live userbot ingestion drill.)

**Sign-off:** ____________________  Date: __________

---

## Deploy-Day Checklist

This single checklist is the authoritative Phase-1 acceptance run. It **supersedes** the per-phase deferred deploy-time UAT lists in `02-UAT.md`, `03-UAT.md`, and `05-UAT.md` — run this, not those.

**Prerequisites (customer-provided, per TZ §7):**
- A production VPS with the stack up: `docker compose -f deploy/docker-compose.yml up -d` (api, worker, beat, userbot, dashboard, postgres, redis, minio, nginx) — see `docs/deployment-guide.md`.
- A real `.env` with: `BOT_TOKEN` (@BotFather), `WEBHOOK_SECRET`, public-HTTPS `PUBLIC_WEBAPP_URL`, `TG_API_ID`/`TG_API_HASH`/`TG_SESSION_STRING` (my.telegram.org + one-time login), `POSTGRES_PASSWORD`, `JWT_SECRET`, S3 creds, `ANTHROPIC_API_KEY`. TLS via certbot.
- The customer's **100-message channel control sample** + `synonyms.json` + a senior trader for §6.1.3 sign-off.
- A live monitored Telegram channel and the userbot account.

```
§6.1.1 — Request ≤10 s / status notify ≤30 s        [requires: BOT_TOKEN + public HTTPS]
  [ ] Web App submit → request in dashboard ≤10 s
  [ ] Status change → client Telegram push ≤30 s

§6.1.2 — UZEX positions, correct fields, ≥95% / ≥50  [committed-sample gate already GREEN]
  [ ] Live UZEX fetch → polymer positions in signals with correct fields
  [ ] (optional) customer UZEX test-day export → pytest test_uzex_accuracy.py ≥95%

§6.1.3 — Channel recall ≥80% / precision ≥85% / 100  [requires: customer 100-msg sample + synonyms + trader + ANTHROPIC_API_KEY]
  [ ] Place 100-message sample at GOLDEN_SET_PATH (+ synonyms.json)
  [ ] Generate predictions (live key) → pytest test_telegram_accuracy.py -m gate → recall ≥80% / precision ≥85%
  [ ] Senior trader signs off §5.3 tolerances

§6.1.4 — Source isolation + failure alert ≤30 min    [requires: live source-failure on VPS]
  [ ] Break one source 3 cycles → exactly one source_failure alert ≤30 min
  [ ] Sibling sources keep producing (isolation); success resets consecutive_failures

§6.1.5 — DB restore on clean server ≤2 h             [requires: rerun on real VPS]
  [ ] Follow runbook §3 on the VPS → stack healthy, wall-clock ≤2 h
  [ ] Post-restore checklist (§4) all ticked

§6.1.6 — Admin add site + channel; failed-test cannot enable  [telegram slice CLOSED locally; requires: live userbot account/channel for ingestion]
  [ ] html_table/rss: configure → Test → ≤10 preview → Enable → signals in feed
  [ ] telegram_channel: live userbot running → post message → raw_items → parsed → signal in feed
  [ ] Enable-gate: source with last_test_ok_at IS NULL → PATCH enable → 422
```

**After the run:** record each result, then re-run `/gsd-verify-work 6` (or `/gsd-audit-uat`) to close these out.

---

## Locally-proven vs deploy-day (summary matrix)

| TZ § | Criterion | Automated evidence (GREEN now) | Remaining: blocked on |
|------|-----------|--------------------------------|------------------------|
| §6.1.1 | request ≤10 s / notify ≤30 s | `test_request_sla.py` (4/4) — proxy | live wall-clock: BOT_TOKEN + public HTTPS |
| §6.1.2 | UZEX ≥95% / ≥50 sample | `test_uzex_accuracy.py` ≥0.95 on 55-position committed sample | *none for committed gate*; optional customer export |
| §6.1.3 | channel recall ≥80% / precision ≥85% / 100 | `test_telegram_accuracy.py -m gate` (≥0.80/≥0.85) on committed example fixture | customer 100-msg sample + synonyms + trader + live key |
| §6.1.4 | source isolation + alert ≤30 min | `test_source_failure_alert.py` + `make smoke` (06-05, ran LIVE: one source_failure alert, sibling isolated) | live source-failure on the VPS |
| §6.1.5 | restore ≤2 h on clean server | `test_restore_local.sh` (06-02, ran LIVE: 4 s vs 7200 s) + validated runbook | rerun on the real VPS (hardware timing) |
| §6.1.6 | admin add site + channel; failed-test cannot enable | `test_telegram_channel_close.py` (06-03, slice CLOSED) + `test_source_wizard.py` (website e2e) | live userbot account/session + live channel (ingestion only) |

**No real secret values appear in this document.**

---

*Phase: 06-acceptance-handover*
*Created: 2026-06-22*
