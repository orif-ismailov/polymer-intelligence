---
phase: 05-telegram-monitoring-ai
reviewed: 2026-06-19T00:00:00Z
depth: standard
files_reviewed: 32
files_reviewed_list:
  - backend/alembic/versions/0003_phase5_ai_extraction.py
  - backend/app/api/admin_sources.py
  - backend/app/api/feed.py
  - backend/app/core/config.py
  - backend/app/ingest/telegram_channel/adapter.py
  - backend/app/models/sources.py
  - backend/app/schemas/dashboard.py
  - backend/app/services/ai_signal_service.py
  - backend/app/services/lead_score_recompute_service.py
  - backend/app/services/userbot_health_service.py
  - backend/app/tasks/celery_app.py
  - backend/app/tasks/nightly_catchup.py
  - backend/app/tasks/parse_telegram.py
  - backend/app/tasks/rescore.py
  - backend/app/tasks/schedule.py
  - backend/app/tasks/userbot_health.py
  - backend/parsing/budget.py
  - backend/parsing/eval_cli.py
  - backend/parsing/extractor.py
  - backend/parsing/fallback.py
  - backend/parsing/lead_scoring.py
  - backend/parsing/prompts/loader.py
  - backend/parsing/schemas.py
  - backend/parsing/text_prep.py
  - dashboard/app/(dashboard)/signals/NeedsReviewChip.tsx
  - dashboard/app/(dashboard)/signals/page.tsx
  - dashboard/components/feed/LiveFeedTable.tsx
  - deploy/docker-compose.dev.yml
  - userbot/channel_registry.py
  - userbot/heartbeat.py
  - userbot/main.py
  - userbot/session.py
findings:
  critical: 5
  warning: 9
  info: 5
  total: 19
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-06-19T00:00:00Z
**Depth:** standard
**Files Reviewed:** 32
**Status:** issues_found

## Summary

Phase 5 implements the Telegram userbot, the LLM extraction pipeline, the Redis
token-budget gate, lead scoring, the nightly catch-up, and the needs_review feed
filter. The prompt-injection separation in the extractor (raw channel text in the
user turn only, Mode.TOOLS schema constraint) is sound, secrets are env-only and
never logged, and the feed/`ai_signal_service` SQL uses bound params throughout.

However, the **entire G4 budget-degrade path is broken at runtime**: the code writes
`parse_status = "budget_deferred"` to a PostgreSQL ENUM column whose type has no such
value, so every `BudgetExceeded` commit will raise a database error. The nightly
catch-up that selects `'budget_deferred'` rows is consequently dead, and even if the
enum value existed, the design produces duplicate signals per raw_item. Separately,
the Phase-5 migration's partial index uses a parser discriminator (`'llm_extract'`)
that does not match anything the code actually writes (`'llm_extract_tools'`), so the
index is permanently empty and the per-source budget query falls back to a sequential
scan. The token-budget gate has a non-atomic check/rollback that can over-spend, and
the SSE endpoint interpolates Redis pub/sub payloads into the event stream without
framing sanitization.

## Critical Issues

### CR-01: `budget_deferred` is not a valid `parse_status` enum value — G4 path crashes on commit

**File:** `backend/app/tasks/parse_telegram.py:253` (also `:315`, `:338`)
**Issue:** On `BudgetExceeded`, the task sets `raw_item.parse_status = "budget_deferred"`.
The `raw_items.parse_status` column is a Postgres ENUM (`PgEnum(ParseStatus, name="parse_status")`,
see `backend/app/models/sources.py:110-115`), and `ParseStatus` (`backend/app/models/enums.py:28-35`)
only defines `pending | parsed | failed | skipped | irrelevant`. No migration adds
`budget_deferred` (verified: `grep "ADD VALUE" alembic/` returns nothing). When the
budget is exhausted, `session.commit()` at line 318/340 will raise
`DataError: invalid input value for enum parse_status: "budget_deferred"`, aborting the
transaction — the rule-based signal is lost and the worker errors out. This breaks
ROADMAP SC#4 / AI-SPEC G4 entirely. It is also unreachable by current tests unless they
mock the DB enum.
**Fix:** Add the enum value via a new migration and the model enum, OR reuse an existing
state. Minimal migration:
```python
def upgrade() -> None:
    op.execute("ALTER TYPE parse_status ADD VALUE IF NOT EXISTS 'budget_deferred'")
```
and add `budget_deferred = "budget_deferred"` to `ParseStatus`. Note `ALTER TYPE ... ADD VALUE`
cannot run inside a transaction block in older PG — set the migration to non-transactional
or commit separately. Re-run the full budget-exceeded integration test against a real DB.

### CR-02: Nightly catch-up selects a state that is never written — recovery path is dead

**File:** `backend/app/tasks/nightly_catchup.py:88-101`
**Issue:** `nightly_llm_catchup` queries `WHERE ri.parse_status = 'budget_deferred'`. Because
CR-01 prevents any row from ever reaching that state (the commit fails before it persists),
this query always returns zero rows. Even after CR-01 is fixed, the bound value
`'budget_deferred'` is compared against the enum column; that comparison is fine once the
enum value exists, but the entire recovery flywheel is currently non-functional. This means
budget-deferred items are never reprocessed with the LLM — silent data loss of the AI
extraction for every message ingested after the daily budget is hit.
**Fix:** Land CR-01 first, then add an integration test that (a) forces `BudgetExceeded`,
(b) asserts the raw_item persists as `budget_deferred`, (c) runs `nightly_llm_catchup` and
asserts the item is re-enqueued and re-parsed.

### CR-03: Budget-deferred + nightly reprocess creates DUPLICATE signals per raw_item

**File:** `backend/app/tasks/parse_telegram.py:300-318` + `backend/app/tasks/nightly_catchup.py:109-131`
**Issue:** On the budget path the task runs `rule_based_extract`, writes a Signal, and (per
the intended design) leaves the item for nightly catch-up. `nightly_llm_catchup` resets
`parse_status` to `'pending'` and re-dispatches `parse_telegram_item`, which runs the LLM
extractor and writes a SECOND Signal for the same `raw_item`. `signals.raw_item_id` has NO
unique constraint (`backend/app/models/signals.py:70-72`), and `create_signal_from_extraction`
does no existing-signal lookup. Result: two feed entries (one rule-based needs_review, one
LLM) for one source message — data duplication that corrupts the feed and per-source spend
accounting.
**Fix:** Make the catch-up path idempotent. Either (a) delete/supersede the rule-based Signal
for the raw_item before re-extracting, or (b) update the existing Signal in place instead of
inserting, or (c) add a partial unique constraint on `signals.raw_item_id` and have the
re-parse update rather than insert. Add a test asserting exactly one Signal per raw_item
after a budget-deferred → catch-up cycle.

### CR-04: Phase-5 partial index never matches — `parser = 'llm_extract'` vs written `'llm_extract_tools'`

**File:** `backend/alembic/versions/0003_phase5_ai_extraction.py:60-65`
**Issue:** The migration creates `ix_parse_runs_llm_created` with
`postgresql_where=sa.text("parser = 'llm_extract'")` (exact equality). But the code never
writes the literal `'llm_extract'`: the extractor uses `PARSER_TOOLS = "llm_extract_tools"`
(`backend/parsing/extractor.py:73`) and `parse_telegram.py` writes `"llm_extract_tools"` /
`"rule_based_fallback"`. The per-source spend query and budget query use
`parser LIKE 'llm_extract%'` (`backend/parsing/budget.py:192,220`). So: (1) the partial index
indexes zero rows forever, (2) the `LIKE 'llm_extract%'` queries cannot use it and fall back
to a sequential scan on `parse_runs`, defeating the index's stated purpose, and (3) the
docstring/comments in `backend/app/models/sources.py:134,143,152` claim the discriminator is
`'llm_extract'`, contradicting the code. This is a correctness/performance defect and a
documented-contract mismatch.
**Fix:** Re-create the index with a predicate matching reality, e.g.
`postgresql_where=sa.text("parser LIKE 'llm_extract%'")`, in a NEW migration (0003 must not be
edited per its own header). Reconcile the `sources.py` comments to `'llm_extract_tools'` /
`'llm_extract_native'`.

### CR-05: Token-budget check/rollback is not atomic — concurrent workers can over-spend

**File:** `backend/parsing/budget.py:130-146`
**Issue:** `check_and_reserve_tokens` issues `INCRBY` then, if over limit, a separate `DECRBY`.
Between the `INCRBY` (line 131-133) and the `DECRBY` rollback (line 140), other prefork workers
run their own `INCRBY`s. Each worker that overshoots rolls back only its own reservation, but a
worker whose `INCRBY` result is read AFTER several concurrent increments may see a `new_total`
far above the limit and still only roll back `estimated_tokens` — meanwhile other workers'
in-flight reservations have already let `extract_signal()` proceed. The module docstring
(lines 9-19) acknowledges "worst case we over-spend by one reservation," but with N concurrent
workers the actual overshoot is up to N reservations, not one — the hard cost cap (AI-SPEC G4 /
T-05-12) is soft. There is no compare-and-set; the limit is not enforced atomically.
**Fix:** Make the gate a single atomic operation via a Lua script (`EVAL`) that reads the
counter, checks the limit, and only `INCRBY`s if it would stay under, returning a boolean.
Example: `if redis.call('GET',KEYS[1]) + ARGV[1] > tonumber(ARGV[2]) then return 0 else
redis.call('INCRBY',KEYS[1],ARGV[1]); redis.call('EXPIREAT',KEYS[1],ARGV[3]); return 1 end`.
This removes the read-modify-write race entirely.

## Warnings

### WR-01: SSE endpoint interpolates raw Redis pub/sub payload into the event stream

**File:** `backend/app/api/feed.py:263-265`
**Issue:** `yield f"data: {msg}\n\n"` writes `msg` (the raw decoded Redis pub/sub message) directly
into the SSE frame. If any publisher ever puts a payload containing a newline into `feed:new`,
it breaks SSE framing (a `\n\n` inside `msg` terminates the event early / injects a fake event the
browser will dispatch). The contract assumes `msg` is a bare entity ref, but nothing here validates
or escapes it. Defense-in-depth for an event stream consumed by `queryClient.invalidateQueries`.
**Fix:** Sanitize before emitting: strip CR/LF and cap length, e.g.
`safe = str(msg).replace("\r", "").replace("\n", "")[:128]; yield f"data: {safe}\n\n"`.

### WR-02: `record_actual_tokens` cannot exceed the daily limit even when the cap is blown

**File:** `backend/parsing/budget.py:149-173` + caller `backend/app/tasks/parse_telegram.py:232-233`
**Issue:** After a successful LLM call the task reconciles with
`record_actual_tokens(LLM_TOKEN_ESTIMATE=400, actual)`. When `actual > reserved` it `INCRBY`s the
delta with no limit check (line 169). The reservation was 400 but `max_tokens=512` plus a padded
≥4096-token cached system prompt means actual `tokens_in + tokens_out` can be several thousand per
call. The 400-token pre-estimate therefore massively under-reserves, so the budget counter routinely
under-counts during the reservation window and the true spend can sail past `DAILY_TOKEN_LIMIT`
before reconciliation catches up. Combined with CR-05 this makes the "hard daily cap" advisory at
best.
**Fix:** Set `LLM_TOKEN_ESTIMATE` to a realistic conservative ceiling (closer to expected
`tokens_in + tokens_out`, accounting for the cached prompt's first-call cost), and treat the
post-call reconciliation as additive only. Document that cache_read tokens are excluded from the
budget intentionally if that is the intent.

### WR-03: Lead-score recompute query references `sa.dialects` without importing it — `AttributeError`/wrong branch

**File:** `backend/app/services/lead_score_recompute_service.py:160`
**Issue:** `sa.cast("{}", sa.dialects.postgresql.JSONB if hasattr(sa, "dialects") else sa.JSON)`.
The module imports `import sqlalchemy as sa` but never `import sqlalchemy.dialects`. `sa.dialects`
is not guaranteed to be populated on the bare `sqlalchemy` namespace unless a dialect submodule was
imported elsewhere; `hasattr(sa, "dialects")` may be False, silently selecting the `sa.JSON` branch
(producing a different cast than intended), or the expression raises `AttributeError` at query-build
time. Also `sa.cast("{}", JSONB) != Signal.ai` is a fragile way to express "ai is not empty" — JSONB
equality of `'{}'` vs a populated object works, but NULL `ai` rows make `Signal.ai != '{}'` evaluate
to NULL (filtered out), which is then redundantly handled by the per-row `if not signal.ai: continue`.
**Fix:** `from sqlalchemy.dialects.postgresql import JSONB` explicitly and drop the `hasattr` guard.
Prefer `Signal.ai.isnot(None)` plus the per-row empty check, or `Signal.ai.op('!=')(sa.text("'{}'::jsonb"))`.

### WR-04: Lead-score recompute pagination can skip stale rows (OFFSET walks a shrinking set is fine, but version filter + offset interact)

**File:** `backend/app/services/lead_score_recompute_service.py:147-200`
**Issue:** The loop selects stale rows with `OFFSET offset LIMIT batch_size`, then UPDATES those
rows so they are no longer stale, then advances `offset += batch_size`. Because the WHERE clause
filters on `scoring_prompt_version != new_version`, every processed row drops OUT of the result set
on the next iteration, so advancing the offset SKIPS `batch_size` not-yet-processed rows each round.
Rows between `offset` and `offset + batch_size` of the *original* set are never visited — they remain
stale. (This is the classic "mutate-while-paginating with OFFSET" bug.)
**Fix:** Do not advance `offset`; always re-query from offset 0 (the filter naturally shrinks the
set), or paginate by keyset on `Signal.id > last_id` instead of OFFSET. Add a test that re-scores a
set larger than one batch and asserts ALL rows reach `new_version`.

### WR-05: Userbot message handler uses `event.chat.username` only — non-username channels and forwards bypass routing

**File:** `userbot/main.py:134-153`
**Issue:** The handler maps incoming messages to a source via `chat.username`. Private channels,
channels referenced by ID, or messages where `get_chat()` returns an entity without `username`
(common for megagroups/linked discussion) are silently dropped (`reason="no_username"`). The
registry (`channel_registry.py`) also keys exclusively on `config->>'username'`. Any enabled source
configured by anything other than a public @username will never ingest, with only a debug log. This
is a silent monitoring gap against ROADMAP SC#1.
**Fix:** Key the registry/handler on the resolved channel/peer ID (stable, always present) in
addition to username, or document/validate at enable-time that only public-username channels are
supported and surface a warning when an enabled source produces zero matches.

### WR-06: `_seconds_until_midnight` has dead/misleading code and a misnamed contract

**File:** `backend/parsing/budget.py:84-99`
**Issue:** Line 92-94 `next_midnight = midnight.replace(hour=0, minute=0, second=0, microsecond=0)`
is a no-op (re-applies the same fields already set on line 90). The function name says "seconds until
midnight" but it returns an absolute UNIX timestamp (used correctly as `EXPIREAT`). The branch
`if now >= next_midnight` is always true at runtime (now is always ≥ today's midnight), so the
`timedelta(days=1)` always fires — correct result, but the conditional is structurally dead and the
local import of `timedelta` inside the branch is awkward.
**Fix:** Simplify to
`next_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)` and
rename to `_next_midnight_ts()`.

### WR-07: `_safe_decimal` / `_map_kind` swallow bad data into silent defaults — fabricated `sell_offer`

**File:** `backend/app/services/ai_signal_service.py:87-95`
**Issue:** `_map_kind` returns `SignalKind.sell_offer` for `None` AND for any unmappable value
(`except ValueError`). A relevant extraction whose `kind` is missing or unrecognized is silently
recorded as a `sell_offer` with no flag, producing a fabricated buy/sell direction in the feed —
exactly the hallucination class the schema validators (T-05-01) are meant to prevent. Since this is
the LLM-trusted path, a wrong kind is a market-data correctness issue, not just a default.
**Fix:** Return `None`/`news` for unknown kinds, or set `needs_review=True` when the kind had to be
defaulted. Do not default an actionable direction.

### WR-08: Userbot performs a DB round-trip + commit per message on the hot path inside a broad try/except

**File:** `userbot/main.py:183-224`
**Issue:** Every incoming message opens a new `SessionLocal()`, runs a raw SQL `SELECT` for the
source row (whose result is then discarded — `_MinimalSource(source_id)` is built from the already-known
`source_id`, line 185-204), and commits. The SELECT is pure overhead (the row is only checked for
existence; `source_obj` doesn't use any of the selected columns). The `import sqlalchemy` is done via
`__import__("sqlalchemy", fromlist=["text"])` inline (line 186-188) which is an obfuscated way to call
`sa.text`. Under message bursts this is N sessions/commits and N redundant queries. (Correctness, not
just perf: the broad `except Exception` at 217 will swallow a commit failure and just log it, so a
message can be silently lost.)
**Fix:** Import `from sqlalchemy import text` at function top; drop the existence SELECT (or replace
with a cheap `SELECT 1`); ensure `save_raw_items` failures are distinguishable from "duplicate"
(idempotent) so genuine write failures are retried, not silently dropped.

### WR-09: `rescore` task returns success-shaped dict on `MaxRetriesExceededError` but logs error level only

**File:** `backend/app/tasks/rescore.py:104-112`
**Issue:** On exhausted retries the task returns `{"status": "error", "rescored_count": 0, ...}` —
which is correct — but partial work from earlier successful batches may already be committed by
`rescore_on_prompt_version_change` flushing per batch while the outer `session.commit()` (line 87)
only runs once at the end. If an exception occurs mid-loop, the per-batch `flush()`es are rolled back
by the surrounding `with SessionLocal()` never committing, so `rescored_count` reported in the success
path could overstate persisted work if commit semantics change. More concretely: the docstring (lines
22-26) claims "Commits after each batch inside the task" but the code commits ONCE after the whole run
(line 87) — a contract mismatch that affects cancellability and memory for very large backfills.
**Fix:** Either commit per batch inside the service/task as documented, or fix the docstring to state
single-commit semantics. Decide whether a mid-run failure should preserve completed batches.

## Info

### IN-01: `eval_cli._print_report` f-string/`.format` nesting is fragile

**File:** `backend/parsing/eval_cli.py:51-52`
**Issue:** `f"  {'D1 Recall (gate ≥{:.0%}):'.format(recall_gate):35s} ..."` mixes an inner `.format`
inside an f-string field. It happens to work because the inner string is `.format`ted first, but it is
hard to read and a refactor (e.g. adding an f-prefix to the inner literal) would raise `KeyError`.
**Fix:** Pre-compute the label: `label = f"D1 Recall (gate ≥{recall_gate:.0%}):"` then `f"  {label:35s} ..."`.

### IN-02: `enqueue_nightly_reprocess` is a no-op with a misleading name and stale docstring

**File:** `backend/app/tasks/parse_telegram.py:132-149`
**Issue:** The function only logs; the docstring describes behavior ("sets parse_status back to
'pending'") that it does not perform and partially contradicts itself. Dead behavioral surface that
implies a queue mechanism that does not exist.
**Fix:** Remove the function or implement the documented behavior; trim the docstring to match.

### IN-03: `parse_telegram.py` writes `parser="llm_extract_tools"` on blank/dead-letter paths that did no LLM call

**File:** `backend/app/tasks/parse_telegram.py:205,266`
**Issue:** The G6 blank-content path and the G3 dead-letter path both journal `parser="llm_extract_tools"`
even though (G6) no LLM call was made and (G3) all attempts failed. This pollutes the
`parser LIKE 'llm_extract%'` spend/attribution query with rows that consumed zero/failed tokens. Not a
spend bug (tokens are 0) but it muddies attribution and the partial-index intent.
**Fix:** Use a distinct discriminator for no-call journaling (e.g. `"skip_blank"`, `"llm_extract_failed"`)
so the spend query and index stay precise.

### IN-04: `FeedItem` TS interface omits `needs_review`, diverging from the Pydantic schema

**File:** `dashboard/components/feed/LiveFeedTable.tsx:33-46`
**Issue:** The backend `FeedItem` now includes `needs_review: bool` (`backend/app/schemas/dashboard.py:46`),
but the TS `FeedItem` interface does not declare it, so the field is dropped client-side and cannot be
surfaced (e.g. a row badge). The filter works, but the per-row review state is invisible. Contract drift
between API and client types.
**Fix:** Add `needs_review: boolean;` to the TS interface and optionally render a row indicator.

### IN-05: Magic confidence/threshold constants scattered across fallback and lead scoring

**File:** `backend/parsing/fallback.py:52-53,327-336` and `backend/parsing/lead_scoring.py:72-97`
**Issue:** Per-field confidence literals (`0.6`, `0.4`, `0.5`) and scoring weights are inline magic
numbers documented only in comments/docstrings. A weight change requires editing literals without a
version bump guard. Low risk but maintainability-relevant given SCORING_PROMPT_VERSION is meant to gate
changes.
**Fix:** Hoist to named module constants grouped near `SCORING_PROMPT_VERSION` so a change is visible and
reviewable alongside the version bump.

---

_Reviewed: 2026-06-19T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
