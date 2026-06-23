---
phase: 06-acceptance-handover
plan: 03
subsystem: testing
tags: [telegram, pytest, parse-telegram, enable-gate, v_live_feed, acceptance, d-03]

# Dependency graph
requires:
  - phase: 04-dashboard-source-constructor
    provides: "server-side enable-gate (is_enabled=true ⇒ last_test_ok_at IS NOT NULL), no-code sources wizard"
  - phase: 05-telegram-monitoring-ai
    provides: "parse_telegram_item orchestrator, ai_signal_service.create_signal_from_extraction, ExtractionResult schema"
provides:
  - "Key-free executable proof of the §6.1.6 telegram_channel slice (D-03)"
  - "Deterministic regression test for the telegram_channel enable-gate (422 on unverified enable)"
  - "Fixture-driven proof that a channel message becomes a v_live_feed-shaped signal (G5 + needs_review boundary)"
  - "Unblocks the SC#5-caveat retirement in the 06-07 capstone"
affects: [06-07-capstone, 06-ACCEPTANCE, sc5-caveat-retirement]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Key-free acceptance close: drive the real orchestrator with every external seam (extract_signal, adapter.test, budget, product/grade lookup, session) mocked — no live MTProto/Anthropic"
    - "v_live_feed contract assertion: map a produced Signal through app.api.feed._row_to_feed_item and validate against the FeedItem schema instead of needing a live DB/view"

key-files:
  created:
    - backend/tests/test_telegram_channel_close.py
  modified: []

key-decisions:
  - "Asserted the pending-source invariant on the Source object handed to db.add (mirroring test_source_wizard) rather than round-tripping a real DB; mocked db.refresh to populate PK/defaults so the router's 201 SourceHealthItem response validates"
  - "Patched create_signal_from_extraction with a side_effect that calls the REAL ai_signal_service.create_signal_from_extraction so the produced Signal carries the true source_id + field mapping (no fabricated assertions)"

patterns-established:
  - "Pattern 1: real-orchestrator + mocked-seams TDD proof for acceptance slices (closes a §6.1.x slice deterministically, key-free)"
  - "Pattern 2: FeedItem-mapping assertion as a stand-in for a live v_live_feed query"

requirements-completed: []

# Metrics
duration: 3 min
completed: 2026-06-22
---

# Phase 6 Plan 03: Channel Close (D-03 / TZ §6.1.6) Summary

**Key-free pytest module proving the full no-code telegram_channel acceptance path — wizard add → enable-gate (422 without a passing test) → fixture MTProto message → `parse_telegram_item` → a signal that satisfies the `v_live_feed` contract — with no real Telegram account or Anthropic call.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-22T09:56:10Z
- **Completed:** 2026-06-22T09:59:16Z
- **Tasks:** 2 (both in one test module)
- **Files modified:** 1 (created)

## Accomplishments
- Closed the §6.1.6 telegram_channel slice locally and deterministically (D-03), retiring the executable blocker behind the SC#5 cross-phase caveat carried since Phase 4.
- Enable-gate chain proven for `telegram_channel`: pending source saved disabled (`is_enabled=False`, `last_test_ok_at=NULL`); PATCH `is_enabled=True` with `last_test_ok_at=NULL` → **422** (T-06-06); passing Test stamps `last_test_ok_at` → PATCH enable → **200**; non-admin POST/PATCH → **403** (T-04-21).
- Message-flow proven: a fixture channel `raw_item` through `parse_telegram_item` writes a `parse_runs` row **before** the signal (G5 attribution invariant), and the produced signal carries the channel `source_id` and the extracted `kind`/`product_id`/`volume`/`price`.
- `v_live_feed` contract proven without a live view: the produced `Signal` maps cleanly through `app.api.feed._row_to_feed_item` to a validated `FeedItem`.
- `needs_review` boundary preserved (T-06-07): `confidence < 0.5` → `ai.needs_review=True`, still appearing in the stream as a flagged entry rather than auto-trusted.

## Task Commits

Each task was committed atomically. This is a TDD test-only plan: the new tests pass against existing Phase 4 / Phase 5 production code (no production change required), so both tasks land as a single `test(...)` commit covering the one interdependent module (shared helpers + `TestTelegramChannelClose` class).

1. **Task 1 (enable-gate) + Task 2 (message → signal → v_live_feed)** — `f9f9fdd` (test)

_No separate GREEN/feat commit: the §6.1.6 production behavior already exists (04 enable-gate, 05 parser); this plan adds the acceptance proof._

## Files Created/Modified
- `backend/tests/test_telegram_channel_close.py` — `TestTelegramChannelClose` (9 tests): pending-source-saved-disabled, enable-gate-rejects-unverified (422), enable-allowed-after-passing-test (200), passing-test-sets-last_test_ok_at, non-admin-create-403, non-admin-enable-403, fixture-message→signal (G5 + fields), signal-satisfies-v_live_feed-contract, low-confidence→needs_review.

## What the new test asserts and how it passes key-free
- **Enable-gate (Task 1):** uses the `_make_staff_user` / `_auth_headers` / `_make_mock_source` / `_make_client_with_user_and_db` pattern from `test_source_wizard.py`. `get_db` is overridden with a `MagicMock` session; `app.ingest.registry.get_adapter` and `adapter.test` are mocked so config validation and the "Test" button never touch MTProto. The 422/200/403 outcomes come from the real `app/api/sources.py` router logic.
- **Message flow (Task 2):** drives the real `parse_telegram_item` orchestrator with `get_session`, `extract_signal`, `check_and_reserve_tokens`, `record_actual_tokens`, `prepare_message_text`, `write_parse_run`, and `delete_existing_signals` patched. `create_signal_from_extraction` is patched with a side_effect that calls the **real** `ai_signal_service.create_signal_from_extraction` (with `match_product`/`extract_grade` mocked) so the produced `Signal` is genuine. `extract_signal` returns a frozen `ExtractionResult` — no Anthropic call. The produced `Signal` is mapped through `app.api.feed._row_to_feed_item` and validated against `FeedItem`, standing in for a live `v_live_feed` query.
- **Key-free:** every external seam is mocked; the module is safe under placeholder env (`ANTHROPIC_API_KEY=sk-ant-ci-placeholder`, `TG_API_ID=0`) and makes zero live MTProto/Anthropic network calls.

## Decisions Made
- Asserted the D-04 pending invariant (`is_enabled=False`, `last_test_ok_at=None`) on the `Source` object handed to `db.add` rather than round-tripping a real DB, mirroring `test_source_wizard.py`. To let the router's `201` `SourceHealthItem` response validate against a `MagicMock` session, `db.refresh` was given a side_effect that populates the server-generated/default columns a real refresh would load (`id`, `consecutive_failures`, `last_fetch_at`, `last_success_at`) — a test-harness fidelity shim, not a production change.
- Used a real `create_signal_from_extraction` (via patched side_effect) so field/attribution assertions reflect production behavior instead of a fabricated mock.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `db.refresh` mock did not populate the 201 response model fields**
- **Found during:** Task 1 (POST /sources pending-source test)
- **Issue:** The real `create_source` router builds and returns a `SourceHealthItem` after `db.refresh(source)`. With a `MagicMock` session, the freshly-added `Source` left `id` and `consecutive_failures` as non-int values, so Pydantic raised `ValidationError` on the 201 response and the test failed.
- **Fix:** Gave `mock_db.refresh` a side_effect that sets `id=99`, `consecutive_failures=0`, `last_fetch_at=None`, `last_success_at=None` — exactly the server-generated/default columns a real `refresh()` loads. The asserted invariant (`is_enabled=False`, `last_test_ok_at=None`) is read from the `Source` object passed to `db.add`, so the shim does not weaken the assertion.
- **Files modified:** backend/tests/test_telegram_channel_close.py
- **Verification:** `pytest tests/test_telegram_channel_close.py -q` → 9 passed.
- **Committed in:** f9f9fdd

**2. [Rule 3 - Blocking] Import grouping (ruff I001) on the new test module**
- **Found during:** ruff gate after writing the module
- **Issue:** `parsing.schemas` (first-party) was grouped with `fastapi` (third-party); ruff `I001` flagged the un-sorted import block.
- **Fix:** `ruff check --fix tests/test_telegram_channel_close.py` split `parsing` into its own first-party import group.
- **Files modified:** backend/tests/test_telegram_channel_close.py
- **Verification:** `ruff check .` → All checks passed.
- **Committed in:** f9f9fdd

---

**Total deviations:** 2 auto-fixed (2 blocking). **Impact on plan:** Both were test-harness/lint blockers internal to the new file. No production code changed; no scope creep. The plan's acceptance criteria were met exactly as written.

## Issues Encountered
None — the production behaviors under test (Phase 4 enable-gate, Phase 5 telegram parser) already existed and behaved as the plan assumed.

## Verification Results
- `cd backend && python -m pytest tests/test_telegram_channel_close.py -q` → **9 passed** (whole module green).
- Full suite `cd backend && python -m pytest -q` → **761 passed, 65 skipped, 4 deselected** (baseline was 752 passed; +9 from this module, no regressions).
- `cd backend && ruff check .` → **All checks passed** (0).
- `cd backend && mypy app/services --ignore-missing-imports` → **Success: no issues** (17 files).
- `cd backend && mypy app/schemas --ignore-missing-imports` → **Success: no issues** (4 files).

## User Setup Required
None — no external service configuration required (the test is key-free by design).

## Next Phase Readiness
- §6.1.6 is closed at the procedure/CI level — the 06-07 capstone can now retire the SC#5 telegram caveat in ROADMAP / 04-CONTEXT, gated on this test passing.
- The real-account live ingestion stays the deploy-day drill (05-UAT item 1), to be recorded in `06-ACCEPTANCE.md` (06-06). No blockers introduced.

## Self-Check: PASSED
- `backend/tests/test_telegram_channel_close.py` — FOUND on disk.
- Commit `f9f9fdd` — FOUND in `git log`.
- All task `<acceptance_criteria>` re-run and green; plan `<verification>` commands all pass.

---
*Phase: 06-acceptance-handover*
*Completed: 2026-06-22*
