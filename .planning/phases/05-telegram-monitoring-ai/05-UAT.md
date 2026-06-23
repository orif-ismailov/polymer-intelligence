---
status: deferred
phase: 05-telegram-monitoring-ai
source: [05-VERIFICATION.md]
started: 2026-06-19
updated: 2026-06-19
---

## Current Test

number: 1
name: Live userbot ingestion drill
expected: |
  With real TG_API_ID/TG_API_HASH/TG_SESSION_STRING in .env and at least one enabled
  telegram_channel source, `docker compose up userbot` connects, subscribes, and writes a
  heartbeat; a new channel message creates a raw_items row (parse_status='pending', fwd_from
  populated for forwards); enabling a second channel is picked up within ~10 min WITHOUT
  restart; stopping the userbot raises a `userbot_silent` alert within ~5 min.
awaiting: customer-provided TG account/API credentials + session string + a live channel

## Tests

### 1. Live userbot ingestion drill (05-02)
expected: |
  End-to-end MTProto ingestion: connect → subscribe → heartbeat → raw_items row on new message
  → channel-reread without restart → silence alert. Requires real TG credentials + live channel.
result: [deferred — gated on customer inputs]

### 2. Real-data TZ §6.1.3 acceptance gate (05-05)
expected: |
  Place the customer 100-message control sample at GOLDEN_SET_PATH (+ real synonyms.json),
  run the refresh path with a live ANTHROPIC_API_KEY to generate frozen predictions for
  prompt_version v1, then `pytest tests/parsing/test_telegram_accuracy.py -m gate` asserts
  relevant-signal recall ≥ 80% (D1) and per-field precision ≥ 85% (D3–D9). Senior trader signs
  off the two §5.3 defaults (price ±0.5% tolerance; synonym-aware grade counts toward the gate).
result: [deferred — gated on customer 100-message control sample + synonym map]

## Summary

total: 2
passed: 0
issues: 0
pending: 0
skipped: 0
blocked: 0
deferred: 2

## Gaps

None. All 15/15 automated must-haves verified (05-VERIFICATION.md). Both items below are
DEFERRED by product decision, not failures — they require gated customer inputs that are not yet
available and are the natural subject of **Phase 6 (Acceptance & Handover)**:

1. Live userbot ingestion drill — needs real TG account/session + a live monitored channel.
2. Real-data 80/85 acceptance gate — needs the customer 100-message control sample + synonym map + trader sign-off.

The deterministic, key-free CI gate runs on committed example fixtures and passes at 100%/100% until
the customer inputs are delivered. When the inputs arrive, run `/gsd-verify-work 5` to execute these.
