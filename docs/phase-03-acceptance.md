# Phase 3: Client Circuit — Acceptance Checklist

**Version:** 1.0  
**Date:** 2026-06-17  
**Phase:** 03-client-circuit  
**Acceptance authority:** Product Owner / technical lead  
**Status:** DEFERRED TO DEPLOY TIME (automated proxy tests cover CI; live drill requires real BOT_TOKEN + public HTTPS URL)

---

## Overview

This document is the live-drill acceptance checklist for the 5 Phase-3 ROADMAP success criteria.
It maps each criterion to a concrete, runnable verification step, cites the applicable SLA from
**TZ §6.1.1** (section 6, item 1: "Заявка, поданная через Web App, появляется в дашборде ≤10 сек;
смена статуса доставляет клиенту уведомление ≤30 сек"), and records the measured PASS/FAIL value.

**Automated CI gate (runs on every push):**
`backend/tests/test_request_sla.py` contains three in-process proxy tests that verify:
- SC#1 proxy: POST→GET create→readback elapsed time < 10.0 s (DB-mocked, no live infra)
- SC#3 proxy: `transition_status` enqueues `apply_async(queue="notify")` with no `countdown`/`eta`
- SC#3 guard: `notify.py` source contains no `time.sleep()` with constant > 1 s

These proxies pass in CI today. The wall-clock live measurements below are deferred to deploy time,
consistent with the Phase-2 (02-07) acceptance deferral precedent.

---

## Prerequisites

Before running the live drill, ensure the following are ready:

1. **Secrets** — a real `BOT_TOKEN` (from @BotFather), `WEBHOOK_SECRET` (random string), and a
   public HTTPS `PUBLIC_WEBAPP_URL` (e.g. via ngrok: `ngrok http 8000`).
2. **`.env` file** — copy and fill `deploy/.env.example` at the repo root:
   ```
   BOT_TOKEN=<real token from BotFather>
   WEBHOOK_SECRET=<random 32-char string>
   PUBLIC_WEBAPP_URL=https://<your-ngrok-subdomain>.ngrok.io
   POSTGRES_PASSWORD=<password>
   S3_ACCESS_KEY=minioadmin
   S3_SECRET_KEY=minioadmin
   S3_BUCKET=polymer-files
   ```
3. **Docker** running with compose plugin available.
4. **Start the stack** (detached, survives after you close the terminal):
   ```bash
   docker compose -f deploy/docker-compose.dev.yml up -d
   ```
   Wait until all containers are healthy:
   ```bash
   docker compose -f deploy/docker-compose.dev.yml ps
   ```
   Expected: postgres, redis, minio, api, worker, beat, nginx all `Up (healthy)` or `Up`.

5. **Register the webhook** — the FastAPI lifespan calls `setup_webhook()` automatically on startup
   when `PUBLIC_WEBAPP_URL` is non-empty. Confirm: `docker compose logs api | grep setup_webhook`.

6. **Telegram client** — a Telegram account that can message your bot.

---

## Compose Stack Verification (pre-drill)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Worker `-Q` includes `notify` | `celery -A app.tasks.celery_app worker ... -Q ingest,parse,notify,default` | _(record)_ | |
| MinIO health-gated before api | `depends_on: minio: condition: service_healthy` | CONFIRMED (03-01 fix) | PASS |
| BOT_TOKEN/WEBHOOK_SECRET/PUBLIC_WEBAPP_URL flow to api+worker | Both services have `env_file: ../.env`; all three vars pass through | CONFIRMED (config.py lines 39-69) | PASS |
| S3_ENDPOINT wired to api+worker | `S3_ENDPOINT: http://minio:9000` in both service environment blocks | CONFIRMED | PASS |
| `polymer-files` MinIO bucket auto-created | `storage_service.ensure_bucket()` called by `upload_request_file` | CONFIRMED (03-01) | PASS |

**compose.dev.yml verdict:** Verified correct — notify queue consumed, MinIO healthy-gated, all env vars flow via `.env`. No changes required.

---

## SC#1 — Request Submission + Backend Queryability (TZ §6.1.1)

**Criterion:** A client opens the Web App, completes the 4-step wizard, and submits; the confirmation shows number REQ-YYYY-MM-DD-NNNNN, and the request is queryable on the backend within ≤10 s.

**This also closes the 03-04 deferred verification:** the wizard submit→REQ-number→confirmation path was deferred from 03-04 Task 3 to this plan; the live drill below is the resolution.

### Steps

1. Open Telegram and send `/start` to your bot.
2. The bot replies with a greeting (RU or UZ per your language_code) and a Web App button.
3. Tap the Web App button — the Web App opens at `PUBLIC_WEBAPP_URL`.
4. Complete the wizard:
   - Step 1: select a product (e.g. PP), enter grade text (e.g. "HDPE 2420D"), volume (e.g. 100 MT).
   - Step 2: optionally set delivery terms.
   - Step 3: optionally add a comment. Tap "Далее".
   - Confirm screen: tap "Отправить" (Submit).
5. Record the REQ number shown on the confirmation screen (format: `REQ-YYYY-MM-DD-NNNNN`).
6. Note `t_submit` (time of tap on Submit).
7. On the backend, query the request:
   ```bash
   # Option A: direct DB query
   docker compose -f deploy/docker-compose.dev.yml exec postgres \
     psql -U pi_user -d polymer_intelligence -c \
     "SELECT number, status, created_at FROM requests ORDER BY created_at DESC LIMIT 1;"
   # Option B: API (requires valid initData header — see auth mechanism below)
   curl -H "X-Telegram-Init-Data: <initData>" http://localhost:8000/api/v1/webapp/requests
   ```
8. Record `t_queryable` (time the SELECT returns the row or the API returns the number).
9. Compute elapsed = `t_queryable - t_submit`.

### Auth Mechanism for API calls (initData)

The `/webapp/*` endpoints require a valid HMAC-signed `X-Telegram-Init-Data` header.
To generate a valid `initData` for testing without the Telegram client:

```python
# Run inside the backend container or in a Python shell with BOT_TOKEN available
import hashlib, hmac, json, time, urllib.parse

BOT_TOKEN = "<your real bot token>"
user_data = {
    "id": 123456789,       # your Telegram user_id
    "first_name": "Test",
    "last_name": "Client",
    "language_code": "ru",
}
init_data_raw = {
    "user": json.dumps(user_data, separators=(",", ":")),
    "auth_date": str(int(time.time())),
}
# Sort and build the data_check_string
data_check_string = "\n".join(
    f"{k}={v}" for k, v in sorted(init_data_raw.items())
)
secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
hash_val = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
init_data_raw["hash"] = hash_val
init_data_encoded = urllib.parse.urlencode(init_data_raw)
print(init_data_encoded)
```

Use the printed string as the `X-Telegram-Init-Data` header value.

### Result

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| REQ number format | `REQ-YYYY-MM-DD-NNNNN` | _(record)_ | |
| Backend queryable elapsed | ≤10 s (TZ §6.1.1) | _(record seconds)_ | |
| Confirmation screen shows REQ number | YES | _(record)_ | |

**Automated CI proxy:** `test_request_readback_within_10s` passes (in-process, DB-mocked) — provides CI gate.

---

## SC#2 — File Upload to MinIO

**Criterion:** The client can attach files (PDF/Excel/JPG, ≤10 MB, ≤5); they land in the MinIO `polymer-files` bucket under `requests/{id}/`; wrong-type or oversize files are rejected.

### Steps

1. In Step 3 of the wizard (or via file upload UI), attach:
   - A valid PDF file (≤10 MB).
   - A valid JPG image (≤10 MB).
2. Complete the wizard and submit.
3. Confirm files appear in MinIO:
   ```bash
   # Using MinIO client (mc) or the web console at http://localhost:9001
   # Login: minioadmin / minioadmin (or your S3_ACCESS_KEY / S3_SECRET_KEY)
   docker compose -f deploy/docker-compose.dev.yml exec minio \
     mc ls --recursive local/polymer-files/requests/
   # Or browse: http://localhost:9001 → polymer-files bucket → requests/{id}/
   ```
4. Attach a `.txt` file — confirm the upload is rejected with an error (invalid_file_type).
5. Attempt to attach a file > 10 MB — confirm rejection (file_too_large).
6. Attach 5 files successfully; attempt a 6th — confirm rejection (too_many_files).

### Result

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| PDF lands in `polymer-files/requests/{id}/` | YES | _(record path)_ | |
| JPG lands in `polymer-files/requests/{id}/` | YES | _(record path)_ | |
| `.txt` file rejected | 422 invalid_file_type | _(record)_ | |
| File > 10 MB rejected | 422 file_too_large | _(record)_ | |
| 6th file rejected | 422 too_many_files | _(record)_ | |

---

## SC#3 — Status Change → Bot Push ≤30 s (TZ §6.1.1)

**Criterion:** A status change delivers a bot push to the client within ≤30 s (TZ §6.1.1). The push shows the D-10 client-facing label and a deep-link Web App button. "Мои заявки" reflects the new status.

**This also closes the 03-05 deferred verification:** the live my-requests list, detail status-history timeline (Asia/Tashkent timestamps), and foreground-refetch were deferred from 03-05 Task 3 to this plan.

### Steps

1. Submit a request and note its database `id` (from the REQ number or DB query).
2. Trigger a status change. Since Phase 4 (dashboard) is not yet built, use a direct DB update:
   ```bash
   docker compose -f deploy/docker-compose.dev.yml exec postgres \
     psql -U pi_user -d polymer_intelligence -c \
     "UPDATE requests SET status='viewed' WHERE id=<request_id>;
      INSERT INTO request_status_history (request_id, from_status, to_status, changed_by)
        VALUES (<request_id>, 'new', 'viewed', NULL);"
   ```
   Then trigger the notify Celery task manually (since the DB update bypasses the service layer):
   ```bash
   docker compose -f deploy/docker-compose.dev.yml exec worker \
     python -c "from app.tasks.notify import send_status_change_notification; \
                send_status_change_notification.apply_async(args=[<request_id>], queue='notify')"
   ```
   Alternatively, use the service layer via a Python shell for a proper transition:
   ```bash
   docker compose -f deploy/docker-compose.dev.yml exec api \
     python -c "
   from app.core.db import engine
   from sqlalchemy.orm import Session
   from app.models.requests import Request
   from app.models.enums import RequestStatus
   from app.services.request_service import transition_status
   with Session(engine) as s:
       req = s.get(Request, <request_id>)
       transition_status(s, req, RequestStatus.viewed)
       s.commit()
   "
   ```
3. Note `t_transition` (time of the status change).
4. Watch Telegram — the bot push should arrive.
5. Note `t_push` (time the push message appears in Telegram).
6. Record the push content: must contain the D-10 label (e.g. "На рассмотрении" for `viewed` in RU)
   and a "Открыть заявку" / "Arizani ochish" inline button.
7. Tap the inline button — it should deep-link to the Web App at `/#/requests/{id}`.
8. In the Web App, navigate to "Мои заявки" — the request should show the new status chip.
9. Open the request detail — the status timeline should show the transition with Asia/Tashkent timestamp.
10. Background the app and re-open it (or change visibility) — list should re-fetch (visibilitychange refetch).

### Result

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| Bot push delivery elapsed | ≤30 s (TZ §6.1.1) | _(record seconds)_ | |
| Push contains D-10 label (not raw status) | YES (e.g. "На рассмотрении") | _(record label)_ | |
| Push has deep-link inline button | YES ("Открыть заявку") | _(record)_ | |
| Deep-link opens correct request in Web App | YES (/#/requests/{id}) | _(record)_ | |
| "Мои заявки" shows new status chip | YES | _(record)_ | |
| Status history timeline shows transition | YES + Asia/Tashkent time | _(record)_ | |
| Foreground-refetch on visibility change | YES | _(record)_ | |

**Automated CI proxy:** `test_status_change_enqueues_notify_promptly` + `test_notify_task_no_long_sleep` pass — provides CI gate.

---

## SC#4 — i18n, Telegram Theme, Bundle Size

**Criterion:** The Web App toggles RU/UZ (default from Telegram language_code), honors Telegram theme vars, and bundle ≤300 KB gzip; first paint observed on throttled 3G profile.

### Steps

1. Open Settings (gear icon or bottom nav) in the Web App.
2. Toggle language from RU to UZ — the entire UI should switch immediately (no reload).
3. Toggle back to RU — same result.
4. Open the request list in UZ — "Мои заявки" should display "Mening arizalarim" (or the UZ equivalent per i18n bundle).
5. Observe that all colors use Telegram theme vars (the UI adapts if you switch Telegram to dark mode).
6. Check bundle gzip size (already measured in 03-05 automated build):

   **Pre-measured in 03-05 build (automated):** largest gzip chunk = 42.8 KB (vendor), well within ≤300 KB gate.
   
   To re-verify:
   ```bash
   cd webapp && npm run build 2>&1 | grep "gzip"
   # All chunks should be < 300 KB gzip total
   ```
7. Simulate 3G in Chrome DevTools (F12 → Network → Throttling: Slow 3G) — note first paint time.

### Result

| Check | Target | Measured | Status |
|-------|--------|----------|--------|
| RU↔UZ toggle works immediately | YES, no reload | _(record)_ | |
| Default language matches Telegram language_code | YES (uz prefix→uz, else ru) | _(record)_ | |
| Telegram dark mode → UI theme adapts | YES (tg-theme vars) | _(record)_ | |
| Bundle gzip largest chunk | ≤300 KB | 42.8 KB (measured 03-05) | PASS |
| First paint on Slow 3G | ≤3 s observed | _(record)_ | |

---

## SC#5 — Bot Greeting + Notify Queue Routing

**Criterion:** The bot greets the client with a Web App button and routes status notifications via the `notify` Celery queue.

### Steps

1. Send `/start` to the bot from a new (never-seen) Telegram account.
2. Confirm the greeting message appears in RU (or UZ per language_code).
3. Confirm the Web App inline button is present.
4. Tap the button — the Web App opens and the client can submit a request.
5. Trigger a status change (see SC#3 steps) and confirm in Celery worker logs:
   ```bash
   docker compose -f deploy/docker-compose.dev.yml logs worker | grep "notify\|send_status_change"
   ```
   Expected: `Received task: send_status_change_notification` processed by the notify queue worker.
6. Confirm the `clients` row was created for the Telegram user:
   ```bash
   docker compose -f deploy/docker-compose.dev.yml exec postgres \
     psql -U pi_user -d polymer_intelligence -c "SELECT id, telegram_user_id, language FROM clients;"
   ```

### Result

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `/start` triggers greeting (RU or UZ) | YES | _(record)_ | |
| Greeting contains Web App button | YES | _(record)_ | |
| Web App opens on button tap | YES | _(record)_ | |
| `clients` row created on /start | YES | _(record)_ | |
| Notify task processed on `notify` queue | YES (worker log confirms) | _(record)_ | |

---

## Summary

| SC | Criterion | CI Gate | Live Drill Status |
|----|-----------|---------|-------------------|
| SC#1 | Request queryable ≤10 s (TZ §6.1.1) | `test_request_readback_within_10s` PASS | DEFERRED TO DEPLOY |
| SC#2 | Files → MinIO bucket, invalid files rejected | Storage validation tests PASS (13/13) | DEFERRED TO DEPLOY |
| SC#3 | Bot push ≤30 s (TZ §6.1.1) | `test_status_change_enqueues_notify_promptly` + `test_notify_task_no_long_sleep` PASS | DEFERRED TO DEPLOY |
| SC#4 | RU/UZ toggle + Telegram theme + bundle ≤300 KB | Bundle measured 42.8 KB gzip (03-05 build) | Bundle PASS; theme/toggle DEFERRED |
| SC#5 | Bot greeting + notify queue routing | Webhook + notify task tests PASS (12/12) | DEFERRED TO DEPLOY |

**Deferral note:** Live wall-clock measurements for SC#1 (≤10 s), SC#3 (≤30 s), and SC#5 (live bot push routing) require a real `BOT_TOKEN` + public HTTPS `PUBLIC_WEBAPP_URL`. These are deferred to the first deploy session, matching the Phase-2 02-07 acceptance precedent. The automated proxy tests in `backend/tests/test_request_sla.py` serve as the CI gate.

---

## Live Results Log

*(Fill in during the deploy-time drill)*

```
Date:
Operator:
Environment: (local ngrok / staging / production)
BOT_TOKEN: REDACTED
PUBLIC_WEBAPP_URL:

SC#1 — t_submit:          t_queryable:          elapsed:          PASS/FAIL:
SC#2 — PDF path:          JPG path:             invalid_rejected: PASS/FAIL:
SC#3 — t_transition:      t_push:               elapsed:          PASS/FAIL:
        D-10 label:
SC#4 — RU/UZ toggle:      theme_adapts:         first_paint:      PASS/FAIL:
SC#5 — /start greeting:   clients_row:          notify_queue:     PASS/FAIL:

Overall: PASS / FAIL / PARTIAL
Notes:
```
