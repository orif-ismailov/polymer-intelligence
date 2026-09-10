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

## Status: browser-verified AND the follow-ups are done — 10.09.2026 ✅

All three checks passed in a real browser through the `chrome-devtools` MCP
server, against the full `make dev` stack (api + worker + beat + portal +
dashboard + infra). Details in «What was verified» below.

The five findings were then decided and worked:

| # | Finding | Decision | State |
|---|---------|----------|-------|
| 1 | Deal opens on a cancelled tender | Refuse with **409 `request_closed`** | done, browser-verified |
| 2 | `substances` empty | Re-seed | fixed locally; **owed on the dev server** |
| 3 | Presigned URL host | Set `S3_PUBLIC_ENDPOINT` | code confirmed correct; **owed on the dev server** |
| 4 | Pre-fix tenders never repaired | **Backfill migration** | `0050`, applied to dev, browser-verified |
| 5 | 56 ungated real-DB failures | **Fix the stale migration tests only** | 8 fixed; **48 still open, untriaged** |

Two things still owed, both needing an operator on the dev server (access here is
read-only): the substances re-seed and `S3_PUBLIC_ENDPOINT`.

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

## What was verified (10.09.2026)

Buyer `imex-owner` / «DIDOX» (id 2, `importer` — buyer-capable, deliberately NOT
seller-capable). Seller `imex-industrial` / «IMEX INDUSTRIAL GROUP CA» (id 1,
`distributor`+`trader`). Both passwords re-issued through the real staff UI
(`/ru/admin/portal-accounts` → «Новый пароль»), then changed at the first-login
gate — no SQL, no token forging.

Tender **REQ-2026-09-10-00001** (request id 4):

| # | Check | Result |
|---|-------|--------|
| — | Filed via `/cabinet/requests/new/1..5` | lands `new` («Опубликован»), 1 history row |
| 1 | After the seller's quote, the buyer's **list** | «Есть предложения» = `offer_sent` ✅ |
| 2 | After accept | «Поставщик выбран» = `matched`, `DEAL-2026-000004` on `/cabinet/deals` ✅ |
| 3 | Status timeline on the detail page | all three rows, not just creation ✅ |

`POST /portal/companies/2/requests/4/responses/4/accept` → **201**, no 500 (so
the Finding-1 guard holds), and `list_console_messages` was empty throughout.

Persisted state — `requests.status = matched`; history exactly
`(NULL→new)`, `(new→offer_sent)`, `(offer_sent→matched)`, `changed_by` NULL on
all three; `deals` row 5 linked to `request_id = 4`. Notifications: the buyer got
**exactly two** `request_status` rows, one per real transition, not three.

Also verified in the browser, not by script:

* **Finding 2 (substances)** — `python -m app.seed` now runs clean through
  `seed_substances` (`skipped=14`); the `KeyError: created` crash is gone and the
  table holds all 14 rows. *Local only — the dev SERVER still needs its re-seed.*
* **Finding 3 (presigned S3)** — `/cabinet/companies/2/manage` → «Скачать»
  307-redirects to a SigV4 URL that returns **200** and renders in Chrome's PDF
  viewer. The signing code is correct; the dev-server issue is purely an empty
  `S3_PUBLIC_ENDPOINT` there. *Not reproducible locally, still owed on the server.*

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

**DECIDED 10.09.2026 — refuse with 409 `request_closed`. Done.**

* `deal_service.RequestNotOpen`, raised from `open_deal_from_response` after the
  `FOR UPDATE`, asking the machine (`matched in VALID_TRANSITIONS[status]`)
  rather than listing dead statuses — one rule, not a second copy of it.
* The `if` around the `matched` transition is gone: the guard has already proved
  the transition is legal, so the silent skip that let the deal open is now the
  refusal itself.
* `api_portal.accept_rfq_response` maps it to **409 `request_closed`**.
* The portal was printing the raw code at the buyer. `features/rfq-response/lib/
  errors.ts` now holds the seller's existing map and a buyer's one, sharing
  `rfqErrorMessage` — extracted from `RfqResponseForm`, not copied — plus three
  new keys in ru/uz/en. The list also refetches on refusal so the page stops
  showing a stale status.
* **Browser-verified** with a genuine stale tab: quote submitted, tender cancelled
  in a second tab, accept clicked in the first → `409 {"detail":"request_closed"}`,
  the alert reads «Тендер закрыт или отменён — выбрать поставщика уже нельзя.»,
  and the database shows request `cancelled`, response still `submitted`, **zero
  deals**. Before this it opened a real deal.
* **The accept button is still rendered on a cancelled tender** — hiding it was
  the option NOT chosen, so the refusal is server-side only. Worth a follow-up.

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

**Status 10.09.2026:** confirmed fixed **locally** — the unified
`python -m app.seed` runs clean to the end (`seed_substances ok — created=0,
updated=0, skipped=14`) and all 14 rows are present. **Still owed on the dev
server**, which is where the empty table was observed.

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

**Status 10.09.2026:** the signing path is confirmed correct **in a real
browser**. `/cabinet/companies/2/manage` → «Скачать» 307s to
`http://127.0.0.1:9000/polymer-files/…?X-Amz-…&X-Amz-SignedHeaders=host`, which
answers **200** and renders in Chrome's PDF viewer. Locally the fallback host IS
browser-reachable, so this reproduces nothing — it only proves the code signs
against the public endpoint as designed. **The `S3_PUBLIC_ENDPOINT` change is
still owed on the dev server**, and server access is read-only, so it needs an
operator.

### 4. The fix does not backfill — pre-fix tenders stay `new` forever  (needs a decision)

The three tenders that existed before the fix are still wrong, and always will
be. Measured on the local dev database after the verification run:

```
 id |        number        | status  | responses | accepted | deals | history
  1 | REQ-2026-09-04-00001 | new     |         1 |        1 |     1 |       1
  2 | REQ-2026-09-08-00001 | new     |         1 |        1 |     1 |       1
  3 | REQ-2026-09-08-00002 | new     |         1 |        1 |     1 |       1
  4 | REQ-2026-09-10-00001 | matched |         1 |        1 |     1 |       3   ← post-fix
```

Each of 1–3 has an **accepted** quote and an **open deal** and still reads `new`
with a single history row. That is QA's original symptom, unchanged — the fix
only governs transitions made from now on.

**Decision needed:** is a one-off data migration wanted (set `matched` +
synthesise the two history rows where an accepted response and a deal exist), or
do we accept that tenders created before 10.09.2026 read wrong forever? On dev
that is 3 rows; the count on prod is unknown and worth checking before deciding.
A backfill has to invent `created_at` for rows that were never written, which is
the argument against it.

**DECIDED 10.09.2026 — write the backfill. Done: migration `0050`.**

Repairs a request only when it has an **accepted quote AND a deal AND** is still
in a status `matched` is legal from. `cancelled`/`closed` rows are deliberately
left alone — that combination is Finding 1's residue, and "repairing" it would
overwrite a cancellation somebody meant.

Nothing is invented: the `offer_sent` row carries the quote's `created_at` and
the `matched` row the deal's. `changed_by` is NULL, as the live path writes it.
No notifications — these transitions happened weeks ago in every sense except the
database's.

`upgrade()` delegates to `backfill(bind)` so it can be tested for real;
`tests/test_migration_0050_db.py` (9 tests) covers the repaired shape, the two
real timestamps, the `offer_sent` short path, both closed statuses, a tender with
no deal, idempotency, and a guard that `_OPEN` still equals the live machine's
`matched` edges.

Applied to the local dev database: requests **1, 2, 3** went `new → matched` with
three-row timelines, and REQ-2026-09-04-00001 now reads «Поставщик выбран» in the
buyer's cabinet where it read «Опубликован» an hour earlier.

### 5. CI never runs the real-database suite — the 56 failures are NOT an artifact  (needs a decision)

The note this file used to carry said the 56 failures were an artifact of one
shared database and «CI gives each job a fresh Postgres service, so they are
expected to pass there». **Both halves are wrong**, and it matters because it
was the reason nobody chased them.

* On a **freshly created** `test_polymer`, the full suite gives the same
  **3188 passed / 56 failed** — byte-identical to the shared-database run. Not
  an ordering effect.
* `tests/test_migration.py` fails **in complete isolation on an empty
  database** (6 of the 6 that touch schema shape). It is simply stale: it
  asserts revision `0001`, «exactly 20 tables» and 14 ENUMs, while head is
  `0049` with ~80 tables. Same for `test_synonyms_migration` (expects `0002`).
* Not a Python-version effect either — reproduced identically under 3.12
  (the CI pin) and 3.14 (what the local venv resolves to).
* **CI is green because it SKIPS all of them.** `tests/conftest.py::_real_db_optin`
  only honours a `DATABASE_URL` containing *both* `localhost` and `test_polymer`;
  CI's names `polymer_intelligence_test`, so all **424** `@requires_real_db`
  tests skip there. The docstring says so outright: «CI has no `test_polymer`,
  so its behaviour is unchanged and the suite stays hermetic there by default.»

So the real-DB suite has 56 standing failures that no gate has ever looked at,
concentrated in `test_registry_verification_db` (9), `test_lab_api` (9),
`test_admin_verification_api` (8) and `test_migration` (6).

**Decision needed:** fix the stale migration tests and triage the rest, or
accept it and say so out loud? Either is defensible; the current state — a gate
that reports green over 424 unrun tests — is the one that is not.

**DECIDED 10.09.2026 — fix the stale migration tests only. Done (8 of 56).**

`3188 passed / 56 failed` → **`3207 passed / 48 failed`** on a fresh database.

* `test_migration.py` no longer transcribes a schema. The head comes from the
  `ScriptDirectory`, the tables and ENUMs from `Base.metadata`, so migration
  `0051` needs no edit here — a transcribed schema is a second copy of the
  migration chain, and this file is the proof it will not be kept in step.
  `test_exactly_20_tables_created` became `test_migrated_tables_match_the_orm`,
  which also catches what the list could not: a model with no migration.
* One of them was never a stale test but a **broken query** —
  `test_v_live_feed_view_exists` selected `viewname` from
  `information_schema.views`, which has no such column (that is `pg_views`), so
  it raised `UndefinedColumn` instead of ever checking for the view.
* `staff_users.role` / the `staff_role` ENUM were dropped by `0044`; the test now
  asserts the replacement (`is_admin` + `staff_page_access`) rather than being
  deleted.
* `test_synonyms_migration.py` targeted `head` when `0002` WAS head. It names
  `0002` now — a test about one migration has to name that migration.

**The other 48 are untriaged and still ungated**, concentrated in
`test_registry_verification_db` (9), `test_lab_api` (9),
`test_admin_verification_api` (8). That is the follow-up.

**Unrelated to IMEX-6**, and confirmed so: the 7 new tests pass on a fresh
database (`test_deal_service_db` + `test_rfq_response_service_db` +
`test_request_service` → 90 passed), and the authoring session measured the
failure set as byte-identical with and without the source change.

## Test-environment notes for whoever picks this up

The authoring session had no docker, so Postgres 16 was run from
`/usr/lib/postgresql/16/bin` directly against a scratch cluster, and Redis via
`redis-server --daemonize yes`. With that:

* baseline on clean `dev` (e3526cd): **3181 passed / 56 failed**
* with the fix: **3188 passed / 56 failed** — failure sets **byte-identical**,
  +7 being the new tests.

Reproduced on docker 10.09.2026: same **3188 / 56**, on both a reused and a
freshly created `test_polymer`. See Finding 5 — those 56 are real, not an
artifact, and CI has never run them.

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
