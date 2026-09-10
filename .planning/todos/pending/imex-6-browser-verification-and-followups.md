---
created: 2026-09-10
title: IMEX-6 — browser-verify the `matched` fix, plus 3 findings it surfaced
area: backend / portal
jira: https://test-41663228.atlassian.net/browse/IMEX-6
branch: claude/refactoring-backend-mi23ae (commit af96c56, branched from dev e3526cd)
files:
  - backend/app/domains/deals/service.py:511    # the `matched` transition
  - backend/app/domains/deals/rfq.py:235        # the `offer_sent` transition
  - backend/app/domains/requests/service.py:155 # VALID_TRANSITIONS
  - backend/tests/test_deal_service_db.py       # 4 new tests
  - backend/tests/test_rfq_response_service_db.py # 3 new tests
---

## Why this file exists

IMEX-6 is **fixed and pushed**, gated on ruff + mypy + the full backend suite
against real Postgres. It is **not browser-verified**: the session that wrote it
had no docker, so no portal and no stack. Per the repo rule in `CLAUDE.md` —
*"A green test suite is not evidence that a change works. Drive it in a real
browser"* — the fix is not done until someone clicks it.

This is the pick-up-cold note for a terminal session that HAS docker.

## What the fix does

Accepting a seller's quote opened the deal and left the tender on `new`, with a
`history` holding only its creation row. Three changes:

1. `rfq.submit` → tender moves `… -> offer_sent` on the FIRST quote (later
   quotes are a no-op).
2. `open_deal_from_response` → performs the `matched` transition.
3. `VALID_TRANSITIONS` admits `offer_sent` and `matched` from `new`/`viewed`,
   because the old ladder made `matched` unreachable from `new` — the exact
   state QA's tender was in.

Expected timeline after the fix: `new -> offer_sent -> matched`, two history
rows, both with `changed_by = NULL` (buyer/supplier are not staff).

## How to verify (the actual task)

```bash
make dev        # infra + migrations + seeds + api + worker + beat + portal + dashboard
```

`make dev` refuses to start on a busy port and takes the whole stack down if any
process dies — a half-stack makes a working feature look broken. It does NOT
start the userbot or the Telegram Web App; neither is needed here.

Then, through the **`chrome-devtools` MCP server** (not curl, not a script —
that is the same rule broken with a better excuse):

1. Sign in to the portal (`http://localhost:5173`) as a **buyer** company.
2. `/cabinet/requests/new/1` → file a purchase request. Confirm it lands as
   **`new`** on `/cabinet/requests/:requestId`.
3. Sign in as a **verified seller** company (needs a seller business role —
   `distributor`/`trader`/`manufacturer`; the gate is
   `company_service.require_business_role`, and a company with no seller role
   is refused with `role_not_allowed`).
4. `/cabinet/market/requests` → find that tender, submit a quote.
5. **Check #1:** back as the buyer, the tender now reads **`offer_sent`**, not
   `new`. This is the half that fixes the tender LIST — the buyer's main
   workspace, which showed everything as `new` however many quotes were in it.
6. As the buyer, accept the quote.
7. **Check #2:** the tender reads **`matched`** and a deal exists on
   `/cabinet/deals`.
8. **Check #3:** the status timeline on the request detail page shows BOTH
   transitions, not just the creation row. This is the literal symptom QA
   reported.

Watch `list_network_requests` for the accept call — a 500 here is the guard
described under Finding 1 failing.

### Then confirm it actually persisted

An HTTP 200 is not proof anything was written.

```sql
-- expect: matched
SELECT id, number, status FROM requests WHERE id = <request_id>;

-- expect exactly two rows: (new, offer_sent) then (offer_sent, matched),
-- changed_by NULL on both
SELECT from_status, to_status, changed_by, created_at
FROM request_status_history
WHERE request_id = <request_id> ORDER BY id;

-- the deal that should exist alongside it
SELECT id, number, status, request_id FROM deals WHERE request_id = <request_id>;
```

Also confirm the buyer got **one** status notification per real transition and
not three — `transition_status` fires with `dedup=False`, which is why the fix
does not walk the intermediate states.

## Findings — NOT fixed, each needs a decision

### 1. A deal opens on a CANCELLED tender  (real bug, pre-existing)

Neither `open_deal_from_response` nor
`POST /portal/companies/{id}/requests/{id}/responses/{id}/accept` checks that
the **request** is still open — only that the **response** is. A buyer who
cancels a tender and then accepts a quote still standing against it (a stale
browser tab is enough) opens a real deal against a cancelled tender.

This predates IMEX-6 and is not caused by it. It mattered here because
`cancelled -> matched` is not in the machine, so an unconditional transition
would have turned a silent oddity into a **500** on the accept endpoint. The fix
therefore asks the machine first:

```python
if RequestStatus.matched in request_service.VALID_TRANSITIONS[request.status]:
```

Pinned by `test_accepting_on_a_cancelled_request_does_not_raise`.

**Decision needed:** should accepting on a `cancelled`/`closed` tender be
refused with a 409 (`request_closed`) instead? That is the correct behaviour but
it is a new refusal, so it was left out of an IMEX-6 fix deliberately.

### 2. `substances` table is empty on dev  (code bug, ALREADY FIXED — needs a re-seed)

From the same QA round. `seed_substances` used `extra={"created": …}`, and
`created` is a reserved `LogRecord` attribute — `logging.makeRecord` raises
`KeyError` rather than shadowing it. Latent while each seeder ran as its own
`python -m` with the root logger at WARNING; once they were unified behind
`python -m app.seed`, which calls `basicConfig()`, it became a crash on the
LAST seeder in the chain. Hence reference ✅, contract-templates ✅,
substances ❌.

Fixed in `564edbe` (keys renamed to `*_count`, plus `tests/test_log_extra_keys.py`
walking the AST of every module under `app/`). That commit predates `a90e3c0`,
whose SigV4 change QA observed live, so **the running image already has it**.

**Action:** just re-seed. `scripts/dev.sh:111` swallows a seed failure into a
warning (`|| warn "seeding failed (continuing)"`), which is how the API came up
on a partially-seeded database in the first place.

```bash
make seed       # or: docker compose exec api python -m app.seed
# expect: seed: seed_substances ok — created=14, updated=0, skipped=0
```

### 3. Presigned S3 URLs point at `http://minio:9000`  (server config, no code change)

Also from that QA round. `get_s3_presign_client()` is correct — it signs with
`S3_PUBLIC_ENDPOINT or S3_ENDPOINT` under SigV4, and all three
`generate_presigned_url` sites use it. The internal host is the documented
fallback for **`S3_PUBLIC_ENDPOINT` being empty** on the server.

```bash
S3_PUBLIC_ENDPOINT=https://dev-api.ai-imex.com   # deploy/env.dev-server.example:105
```

Two non-obvious constraints the code depends on:

* **No path component.** SigV4 signs host AND path; nginx exposes the bucket at
  `location /polymer-files/`.
* nginx must forward the host EXACTLY as the client sent it — `host` is in
  `X-Amz-SignedHeaders`, so any rewrite is a 403 `SignatureDoesNotMatch`. The
  bucket location already does this and uses **`$http_host`, not `$host`**
  (`deploy/nginx/nginx.dev-server.behind-proxy.conf:107`): `$host` drops the
  port, so a public endpoint on a non-default port is forwarded without it and
  MinIO refuses. Do not "tidy" that into `$host` to match the other blocks —
  the comment above it records that this exact 403 was already hit once.

A presigned URL cannot be rewritten after signing, which is why this has to be
config at signing time rather than a proxy rewrite. Verify by opening a contract
document link in a real browser, not with curl — the `Host`-header behaviour is
exactly what passes a script and fails a real request.

## Test-environment notes for whoever picks this up

The authoring session had no docker, so Postgres 16 was run from
`/usr/lib/postgresql/16/bin` directly against a scratch cluster, and Redis via
`redis-server --daemonize yes`. With that:

* baseline on clean `dev` (e3526cd): **3181 passed / 56 failed**
* with the fix: **3188 passed / 56 failed** — failure sets **byte-identical**,
  +7 being the new tests.

Those 56 are pre-existing in that setup and largely artifacts of one SHARED
database (e.g. `test_synonyms_migration` expects revision `0002` and finds head
`0049`, because another module's `migrate_head()` ran first). CI gives each job
a fresh Postgres service, so they are expected to pass there. **Re-run the suite
in docker to confirm that** — if the count is not 0 failures on a clean per-job
database, that is its own finding and unrelated to this change.

All 7 new tests are `@requires_real_db`, so they SKIP silently without
`DATABASE_URL` naming a localhost `test_polymer`:

```bash
cd backend
DATABASE_URL=postgresql+psycopg://postgres:test@localhost:5432/test_polymer \
  uv run pytest tests/test_deal_service_db.py tests/test_rfq_response_service_db.py -q
```

They were confirmed to FAIL without the source change (stash it and re-run) —
worth repeating if you touch them, since a `@requires_real_db` test that skips
looks identical to one that passes.
