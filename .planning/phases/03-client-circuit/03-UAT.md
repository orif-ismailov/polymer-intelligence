---
status: testing
phase: 03-client-circuit
source: [03-VERIFICATION.md]
started: 2026-06-17T00:00:00Z
updated: 2026-06-17T00:00:00Z
deferral: deploy-time (user-approved 2026-06-17, Phase-2 02-07 precedent)
note: >
  All three items are LIVE-environment checks that require a real BOT_TOKEN and a
  public HTTPS PUBLIC_WEBAPP_URL. They were explicitly deferred to the first deploy
  session by user sign-off at the 03-06 checkpoint. The automated SLA proxy tests
  (backend/tests/test_request_sla.py, 4/4 PASS) plus the bundle-size measurement
  (42.8 KB gzip) serve as the CI gate. Run `/gsd-verify-work 3` at deploy time to
  execute these and close the phase's human-verification debt.
---

## Current Test

number: 1
name: Wizard visual flow + Telegram integration (deferred from 03-04 Task 3)
expected: |
  Home focal point ("Оставить заявку") correct; per-step zod blocking validation;
  BackButton preserves state; client-side file limits (PDF/Excel/JPG, ≤10 MB, ≤5)
  enforced; confirmation shows REQ-YYYY-MM-DD-NNNNN number; theme adapts light/dark
  via var(--tg-theme-*).
awaiting: deploy-time verification (deferred)

## Tests

### 1. Wizard visual flow + Telegram integration (deferred from 03-04 Task 3)
expected: Home focal point correct; per-step zod blocking validation; BackButton preserves state; file limits enforced client-side; confirmation shows REQ number; theme adapts light/dark.
why_human: Visual/interaction correctness of the wizard inside the Telegram Web App cannot be verified by grep or build.
result: [pending — deferred to deploy]

### 2. My-requests list, detail timeline, and language toggle (deferred from 03-05 Task 3)
expected: List newest-first with correct D-10 status chips; detail timeline shows Asia/Tashkent timestamps; language toggle switches UI immediately and persists.
why_human: Visual rendering of statuses, timezone display, and the live language switch cannot be verified without running the app in Telegram against the backend.
result: [pending — deferred to deploy]

### 3. Live end-to-end client-circuit drill (deferred from 03-06 Task 3)
expected: |
  SC#1: wizard submit → REQ number → queryable ≤10 s.
  SC#2: PDF/JPG land in the MinIO polymer-files bucket; invalid types/sizes rejected (422).
  SC#3: status change → bot push ≤30 s with D-10 label + deep-link button.
  SC#4: RU↔UZ toggle + Telegram theme adaptation; first paint ≤3 s on 3G.
  SC#5: /start greeting + Web App button; new account creates a clients row.
why_human: Requires a real BOT_TOKEN + public HTTPS PUBLIC_WEBAPP_URL. Deferred to first deploy session per Phase-2 02-07 precedent. Automated SLA proxy tests (test_request_sla.py 4/4 PASS) serve as the CI gate.
result: [pending — deferred to deploy]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
