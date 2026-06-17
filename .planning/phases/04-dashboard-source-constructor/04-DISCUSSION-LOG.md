# Phase 4: Dashboard + Source Constructor - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-17
**Phase:** 4-dashboard-source-constructor
**Areas discussed:** AI fields without AI, Source constructor scope, Alerts + delivery, Request actions

---

## AI fields without AI (Phase-5 boundary)

### AI render strategy
| Option | Description | Selected |
|--------|-------------|----------|
| Graceful placeholder | Render sections final-shape with "available after Phase 5" empty state | ✓ |
| Hide until Phase 5 | Conditionally hide AI-only sections until data exists | |
| Rule-based stub | Compute non-LLM proxies now, replaced by LLM in Phase 5 | |

**User's choice:** Graceful placeholder (D-01)

### Price-vs-avg (non-AI)
| Option | Description | Selected |
|--------|-------------|----------|
| Yes, compute now | Compute target-vs-market-average from price_points (no AI) in Phase 4 | ✓ |
| Defer to Phase 5 | Treat whole AI block as one unit, wait for Phase 5 | |

**User's choice:** Yes, compute now (D-02)

### Sequencing / decomposition
| Option | Description | Selected |
|--------|-------------|----------|
| Flagship-first | Build Purchase Requests master-detail + feed first | |
| Foundation-first | Shared shell (sidebar, shadcn/ui, Query client, SSE hook, layout) wave 1, then parallel features | ✓ |
| You decide | Leave to planner | |

**User's choice:** Foundation-first (D-03)

---

## Source constructor scope

### Which source types testable/enableable in Phase 4
| Option | Description | Selected |
|--------|-------------|----------|
| html_table/rss live now | html_table+rss fully work; telegram_channel+llm_page config-saved, Test/enable gated to Phase 5 | ✓ |
| All 4 testable now | Pull Phase-5 work forward so all four Test/enable in Phase 4 | |
| Config-only wizard | Generic wizard; only uzex/cbu truly testable | |

**User's choice:** html_table/rss live now (D-04)
**Notes:** Makes literal "telegram-channel signals appear" portion of SC#5 a Phase-5/6 acceptance item — flagged in CONTEXT `<domain>`.

### Pending-type UX
| Option | Description | Selected |
|--------|-------------|----------|
| Saved-pending state | Save config + "Pending activation (Phase 5)" badge, disabled Test/enable | ✓ |
| Hide those types | Only show types whose engine exists in Phase 4 | |

**User's choice:** Saved-pending state (D-05)

### Test preview content
| Option | Description | Selected |
|--------|-------------|----------|
| Parsed signal drafts | Up to 10 normalized rows as they'd land | ✓ |
| Raw rows only | Pre-normalization raw fetched rows | |

**User's choice:** Parsed signal drafts (D-06)

---

## Alerts + delivery

### Rule-builder predicate set
| Option | Description | Selected |
|--------|-------------|----------|
| Show all, mark AI ones | Full predicate set; lead_score_gte labeled "activates with Phase-5 AI" | ✓ |
| Non-AI predicates only | Omit lead_score_gte until Phase 5 | |

**User's choice:** Show all, mark AI ones (D-07)

### Delivery target registration
| Option | Description | Selected |
|--------|-------------|----------|
| Per-rule channel config | chat_ids/group ids entered in the rules builder | ✓ |
| Staff Telegram linking | Staff link Telegram; rules target by role/user | |
| You decide | Leave to research/planning | |

**User's choice:** Per-rule channel config (D-08)

### Team alert bot
| Option | Description | Selected |
|--------|-------------|----------|
| Reuse client bot | Same aiogram bot/token/webhook + notify/deliveries queue | ✓ |
| Separate team bot | Distinct bot/token for internal delivery | |

**User's choice:** Reuse client bot (D-09)

---

## Request actions (flagship)

### Contact Buyer behavior
| Option | Description | Selected |
|--------|-------------|----------|
| Deep-link to Telegram | tg://·t.me deep link to buyer + audit_log contact event | ✓ |
| Record-only action | Log "contacted" + advance status, no outbound link | |
| You decide | Leave to research/planning | |

**User's choice:** Deep-link to Telegram (D-11)

### Action → status-machine mapping
| Option | Description | Selected |
|--------|-------------|----------|
| Buttons drive transitions | open→viewed, Contact→in_progress, Mark Processed→closed, dropdown for rest | ✓ |
| Explicit status control only | Single status dropdown; buttons are shortcuts | |

**User's choice:** Buttons drive transitions (D-12)

### Action set in scope (multi-select)
| Option | Description | Selected |
|--------|-------------|----------|
| Status change | Change status with valid-transition enforcement | ✓ |
| Assign owner | Assign to staff_user (assigned_to) | ✓ |
| Add note | Free-text internal team-only note | ✓ |
| Contact Buyer | Primary contact action | ✓ |

**User's choice:** All four (D-10)

---

## Claude's Discretion

- Export format (CSV vs Excel) on the Purchase Requests table
- SSE-vs-polling build priority (SSE + 30 s polling locked; polling-first-then-SSE is a planning call)
- Keyset pagination by (event_at, id), role-based screen/action gating, shadcn/ui selection,
  dark-theme token wiring, KPI-card data sources

## Deferred Ideas

- Staff Telegram linking subsystem (deferred in favor of per-rule chat_id config; revisit if error-prone)
- Rule-based lead/hot-lead stub (rejected for honest placeholders; Phase 5 delivers real scoring)
- telegram_channel + llm_page live Test/enable (deferred to Phase 5 where engines are built)
