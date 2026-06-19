---
phase: 05-telegram-monitoring-ai
fixed_at: 2026-06-19T00:00:00Z
review_path: .planning/phases/05-telegram-monitoring-ai/05-REVIEW.md
iteration: 1
findings_in_scope: 14
fixed: 13
skipped: 1
status: partial
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-06-19T00:00:00Z
**Source review:** .planning/phases/05-telegram-monitoring-ai/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 14
- Fixed: 13
- Skipped: 1

All fixes were applied in an isolated git worktree, committed atomically, and
verified with the affected test files plus the full backend suite. The full
suite is green except the 2 documented pre-existing router-introspection
failures (`test_prices_api.py::test_prices_path_mounted`,
`test_source_wizard.py::test_sources_router_mounted`), which are unrelated to
these findings.

## Fixed Issues

### CR-01: `budget_deferred` is not a valid `parse_status` enum value
**Files modified:** `backend/app/models/enums.py`, `backend/alembic/versions/0004_phase5_budget_deferred_and_index_fix.py`, `backend/tests/test_migration_0003.py`
**Commit:** 83c90f1
**Applied fix:** Added `budget_deferred = "budget_deferred"` to the `ParseStatus`
StrEnum and created migration 0004 (down_revision=0003) that runs
`ALTER TYPE parse_status ADD VALUE IF NOT EXISTS 'budget_deferred'` inside an
Alembic `autocommit_block()` (ADD VALUE cannot run in a transaction). Updated the
revision-chain test (`test_0003_is_head` → `test_0003_is_not_head_after_0004`)
and added a `TestMigration0004RevisionChain` suite. The G4 budget-degrade commit
no longer raises `DataError`.

### CR-02: Nightly catch-up selects a state that is never written
**Files modified:** (none — resolved transitively by CR-01)
**Commit:** 83c90f1 (CR-01)
**Applied fix:** CR-02 was a downstream symptom of CR-01: once `budget_deferred`
is a valid enum value the BudgetExceeded commit persists, so the
`WHERE ri.parse_status = 'budget_deferred'` query in `nightly_llm_catchup`
returns the deferred rows and the recovery flywheel works. No additional code
change was needed; the existing nightly catch-up query/reset logic is correct.
**Note:** requires human verification — the end-to-end budget→defer→nightly
reprocess cycle should be confirmed against a live DB at deploy time.

### CR-03: Budget-deferred + nightly reprocess creates duplicate signals
**Files modified:** `backend/app/tasks/parse_telegram.py`
**Commit:** 254a8a0
**Applied fix:** Added `delete_existing_signals(session, raw_item_id)` and call it
right before writing the new Signal in `parse_telegram_item`. On the normal first
pass it deletes nothing; on a nightly catch-up reprocess it supersedes the stale
rule-based Signal so exactly one Signal exists per raw_item after a
budget-deferred → catch-up cycle.
**Note:** requires human verification — logic change to the signal-write path.

### CR-04: Phase-5 partial index never matches (`'llm_extract'` vs `'llm_extract_tools'`)
**Files modified:** `backend/alembic/versions/0004_phase5_budget_deferred_and_index_fix.py`, `backend/app/models/sources.py`
**Commit:** 83c90f1 (index), 72e8557 (comments)
**Applied fix:** Migration 0004 drops and recreates `ix_parse_runs_llm_created`
with `postgresql_where=sa.text("parser LIKE 'llm_extract%'")` so it matches the
written discriminators (`llm_extract_tools` / `llm_extract_native`) and can serve
the `LIKE 'llm_extract%'` spend queries. 0003 was treated as immutable (its own
header forbids editing). Reconciled the misleading `ParseRun` docstring/column
comments in `sources.py`.

### CR-05: Token-budget check/rollback is not atomic
**Files modified:** `backend/parsing/budget.py`, `backend/tests/parsing/test_budget.py`
**Commit:** 1be4f27
**Applied fix:** Replaced the non-atomic INCRBY-then-DECRBY-rollback with a single
server-side Lua `EVAL` compare-and-set (`_RESERVE_LUA`) that reads the counter,
checks the limit, and only INCRBYs + sets the midnight EXPIREAT if the
reservation stays under the cap (returns -1 on rejection). This removes the
read-modify-write race that allowed N concurrent workers to overshoot the daily
cap by up to N reservations. Updated the budget tests to the new EVAL-based API.
**Note:** requires human verification — concurrency/atomicity behavior is best
confirmed against a real Redis under concurrent load.

### WR-01: SSE endpoint interpolates raw Redis pub/sub payload
**Files modified:** `backend/app/api/feed.py`
**Commit:** 6962c52
**Applied fix:** Sanitize before framing — `safe = str(msg).replace("\r", "").replace("\n", "")[:128]`
then `yield f"data: {safe}\n\n"`. Strips CR/LF that would break SSE framing and
caps the length defensively.

### WR-02: `record_actual_tokens` under-reserves with a 400-token estimate
**Files modified:** `backend/app/tasks/parse_telegram.py`, `backend/app/tasks/nightly_catchup.py`
**Commit:** 1e3ea4c
**Applied fix:** Raised `LLM_TOKEN_ESTIMATE` from 400 to 1200 (a realistic
conservative ceiling for non-cached `tokens_in + tokens_out`, with cache_read
explicitly excluded by design). Updated the nightly catch-up batch-budget comment
(200 items × 1200 = 240,000 tokens, within the 500K daily budget).

### WR-03: Lead-score recompute references `sa.dialects` without importing it
**Files modified:** `backend/app/services/lead_score_recompute_service.py`
**Commit:** 2a10b0d
**Applied fix:** Added `from sqlalchemy.dialects.postgresql import JSONB` and
replaced the fragile `sa.dialects.postgresql.JSONB if hasattr(sa, "dialects") else sa.JSON`
guard with an explicit `sa.cast("{}", JSONB)`.

### WR-04: Lead-score recompute pagination skips stale rows (OFFSET mutate-while-paginating)
**Files modified:** `backend/app/services/lead_score_recompute_service.py`, `backend/tests/test_lead_score_recompute.py`
**Commit:** 2a10b0d
**Applied fix:** Replaced OFFSET pagination with keyset pagination
(`Signal.id > last_id`). Updating a row drops it out of the stale filter, so an
advancing OFFSET skipped whole batches of unprocessed rows; the keyset walk visits
every stale row exactly once and never loops forever on un-updatable rows (empty
ai / scoring errors). Updated the test mock to the new chain and added a
multi-batch keyset test asserting all rows reach `new_version`.
**Note:** requires human verification — pagination logic change.

### WR-06: `_seconds_until_midnight` has dead/misleading code
**Files modified:** `backend/parsing/budget.py`
**Commit:** 1be4f27 (with CR-05)
**Applied fix:** Simplified to
`now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)` and
renamed `_seconds_until_midnight` → `_next_midnight_ts` to match the contract (it
returns an absolute UNIX timestamp used as EXPIREAT). No other call sites
referenced the old name.

### WR-07: `_map_kind` fabricates `sell_offer` for unknown/missing kinds
**Files modified:** `backend/app/services/ai_signal_service.py`
**Commit:** d096149
**Applied fix:** `_map_kind` now returns the non-directional `SignalKind.news` for
both `None` and unmappable values, so an unknown kind never invents a buy/sell
direction in the feed.

### WR-08: Userbot per-message DB round-trip + obfuscated import
**Files modified:** `userbot/main.py`
**Commit:** 7aac4f3
**Applied fix:** Added `import sqlalchemy as sa` to the function-local import block
and replaced the obfuscated `__import__("sqlalchemy", fromlist=["text"])`. Replaced
the discarded 8-column existence SELECT with a cheap `SELECT 1 FROM sources WHERE id = :id`.
**Partial:** the review also noted the broad `except Exception` can swallow a
commit failure (silent message loss). Distinguishing genuine write failures from
idempotent duplicates so they can be retried requires a retry-semantics design
decision and was not changed here; the import + redundant-SELECT defects are
fixed.

### WR-09: `rescore` docstring claims per-batch commit but code commits once
**Files modified:** `backend/app/tasks/rescore.py`
**Commit:** 4b46881
**Applied fix:** Corrected the docstring to state single-commit semantics: the
service flushes per batch but the task commits once after the run, so a mid-run
failure rolls back all batches and `rescored_count` never overstates persisted
work. (Docstring-vs-behavior reconciliation; the chosen non-risky option of the
two the review offered.)

## Skipped Issues

### WR-05: Userbot message handler keys on `event.chat.username` only
**File:** `userbot/main.py:134-153`
**Reason:** skipped — needs a product/design decision. The review's primary fix is
to re-key the channel registry and message handler on the resolved channel/peer
ID (a stable identifier) in addition to username, OR to validate at enable-time
that only public @username channels are supported. Both touch the source
configuration contract (`config->>'username'` in `channel_registry.py`) and the
subscription/routing model: deciding whether ID-based sources are supported, how
they are configured, and how the registry/subscription loop resolves them is a
product decision beyond a safe automated edit. Left for human design.
**Original issue:** Private/ID-referenced channels and forwards whose `get_chat()`
returns no username are silently dropped (`reason="no_username"`), a silent
monitoring gap against ROADMAP SC#1.

---

_Fixed: 2026-06-19T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
