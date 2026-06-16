# Phase 3: Client Circuit - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-16
**Phase:** 3-client-circuit
**Areas discussed:** Wizard behavior, Bot messages & pushes, File upload flow, Client status visibility

---

## Wizard behavior

| Question | Options | Selected |
|----------|---------|----------|
| Draft persistence | Client-only until submit ✓ / Server-side resumable drafts | Client-only |
| Minimum required to submit | Product + grade/type + volume ✓ / Also require price + Incoterms | Minimal |
| Validation timing | Per-step (block advance) ✓ / Validate at submit | Per-step |

**Notes:** Short 4-step flow; submit-or-lose is acceptable. Files attach after request creation.

---

## Bot messages & pushes

| Question | Options | Selected |
|----------|---------|----------|
| Bot language | Follow client RU/UZ pref ✓ / Russian only (MVP) | Follow pref |
| Status push detail | Detailed + open button ✓ / Minimal + open button | Detailed |
| Greeting / menu | Greeting + persistent Web App button ✓ / Inline Web App button only | Greeting + persistent |

**Notes:** Aligns with dev-spec §4.1 (aiogram webhook, /start greeting, templates {ru,uz}). ≤30 s push SLA.

---

## File upload flow

| Question | Options | Selected |
|----------|---------|----------|
| Upload path | Presigned direct-to-MinIO (initial) → **overridden** / Proxied through backend ✓ | Proxied (post-conflict) |
| Limit enforcement | Client + backend authoritative ✓ / Client-side only | Client + backend |
| telegram_file_id fallback | Bot-sent files only ✓ / MinIO with TG fallback on failure | Bot-sent only |

**Notes:** Initially chose presigned direct-to-MinIO, but dev-spec §4.2 had already resolved
this as **backend-proxied multipart → MinIO with magic-byte MIME validation**. Surfaced the
conflict; user chose to **align with the dev-spec**. Final: proxied upload + magic-byte MIME,
≤10 MB, ≤5.

---

## Client status visibility

| Question | Options | Selected |
|----------|---------|----------|
| Statuses shown | Simplified client-facing map ✓ / All 7 translated verbatim | Simplified map |
| Detail view | Full timeline w/ timestamps ✓ / Current status only | Full timeline |

**Notes:** 7 internal statuses → cleaner client set (RU/UZ); history timeline in Asia/Tashkent.

---

## Claude's Discretion

- Request number generation (`REQ-…-NNNNN` via per-date DB sequence, dev-spec §3)
- initData verification mechanics (X-Telegram-Init-Data, HMAC per request, TTL 24 h — locked by REQ)
- Status-machine transition validation (dev-spec §3)
- Performance-budget tactics (≤3 s first paint / ≤300 KB gzip / ≤10 s request-appears)

## Deferred Ideas

- Server-side resumable wizard drafts (deferred — client-only chosen for MVP)
- Published reports in the Web App (`GET /webapp/reports`) — future milestone per dev-spec
