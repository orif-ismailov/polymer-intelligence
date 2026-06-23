# Phase 4: Dashboard + Source Constructor - Context

**Gathered:** 2026-06-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the internal team's live working surface (Next.js dashboard, Surface B) plus the
no-code source constructor. In scope: the unified Live Market Feed (`v_live_feed`) with
filters + real-time refresh, the **flagship Purchase Requests master-detail** screen with
team actions, the Price Trends chart (`price_points`, Recharts), source health + enable/disable,
the add-source wizard (auto-form from adapter `config_schema` → Test → enable), and alert
rules builder + Telegram delivery to the team. Requirements: REQ-live-feed (FR-10),
REQ-purchase-requests (FR-11), REQ-price-trends (FR-12), REQ-alerts (FR-14), REQ-bot-team
(FR-16), REQ-source-builder (FR-22).

**Out of scope (other phases):** LLM extraction + lead scoring (Phase 5, REQ-ai-extraction /
REQ-lead-scoring) — so `requests.ai`/`signals.ai` are empty in Phase 4; the Telethon userbot
and `telegram_channel` monitoring (Phase 5, REQ-telegram-monitoring); published reports /
`/reports` approve flow and `/counterparties` (Future Milestone). The public landing page
(Surface A) and Web App (Surface C, Phase 3) are not rebuilt here.

**Cross-phase boundary note (affects acceptance) — RETIRED 2026-06-22:** Roadmap SC#5 reads
"an admin adds a new public website AND a new Telegram channel … its signals subsequently
appear in the feed." This boundary note (carried since Phase 4) is now **RETIRED**: the
`telegram_channel` slice was closed locally in Phase 6 by 06-03
(`backend/tests/test_telegram_channel_close.py`, 9 passed — wizard add → enable-gate 422 until
Test passes → fixture MTProto message → `parse_telegram_item` → signal in `v_live_feed`,
key-free). Live-account ingestion remains the deploy-day drill in
`.planning/phases/06-acceptance-handover/06-ACCEPTANCE.md`. Historical text preserved below for
the audit trail:

> ~~Because the userbot and `llm_page` LLM extraction land in Phase 5, **the literal
> "telegram-channel signals appear in feed" portion of SC#5 is satisfied in Phase 5/6, not
> Phase 4.** Phase 4 delivers the full wizard + website (`html_table`/`rss`) onboarding
> end-to-end; `telegram_channel`/`llm_page` are config-saveable in a pending state (see D-04..D-06).
> Verifier/roadmap should treat that slice of SC#5 as a Phase-5/6 acceptance item.~~
</domain>

<decisions>
## Implementation Decisions

### AI-dependent UI under a Phase-4 world (AI engine not built yet)
- **D-01:** AI-only elements (request-detail AI Analysis: Match Score / Demand Level /
  Recommendation; the home **AI Market Signals** panel; the **Hot Leads** KPI) render in their
  **final-shape layout with a graceful empty/placeholder state** ("AI analysis available after
  Phase 5" / "pending"). No hidden sections and no dead-end blank cards — Phase 5 just fills the
  data. (Hide-until-Phase-5 and rule-based-stub options were considered and rejected.)
- **D-02:** The AI block's **Price Analysis line (target price vs. market average) IS computed
  for real in Phase 4** from `price_points` — it needs no LLM and is the one genuinely useful
  AI-block field available now. Treat it as a non-AI field, not part of the deferred AI block.

### Phase sequencing / decomposition (guidance for planner)
- **D-03:** **Foundation-first.** Wave 1 builds the shared dashboard shell — left sidebar nav,
  shadcn/ui setup (not yet installed), TanStack Query client, the SSE/polling refresh hook,
  and the auth-guarded app-router layout — then feature screens build in parallel waves on top.
  (Flagship-first was considered; foundation-first chosen to reduce rework across 6 requirements.)

### Source constructor scope (cross-phase with Phase 5)
- **D-04:** **`html_table` + `rss` are fully live in Phase 4**: the wizard auto-form from
  `config_schema`, a real **Test** (live fetch + parse), preview, and enable-on-pass all work
  end-to-end for these types. `telegram_channel` + `llm_page` are **wizard-configurable and
  saved, but their Test/enable are gated** until their engines exist in Phase 5 (preserves the
  `is_enabled = true ⇒ last_test_ok_at IS NOT NULL` invariant — they stay `is_enabled=false`).
- **D-05:** Pending types show a **"Pending activation (Phase 5)" badge** in the sources list
  with disabled Test/enable controls, so an admin can pre-stage channel/LLM-page config now and
  it goes live when the engine ships. (Hiding those types from the picker was rejected — admins
  should be able to pre-stage.)
- **D-06:** The Test preview renders **parsed signal drafts** — up to 10 normalized rows as they
  would land (product / grade / volume / price / currency / section / event_at), so the admin can
  judge extraction quality before enabling (TZ §6.1.6 / FR-22 intent). Not raw pre-normalization rows.

### Alerts + team delivery
- **D-07:** The rule builder **exposes the full Phase-1 predicate set** (`kind`, `product_id`,
  `volume_gte`, `urgency_in`, `source_kind`, `lead_score_gte`), but `lead_score_gte` is **labeled
  "activates with Phase-5 AI"** — rules can be authored now; that predicate simply won't match
  until lead scoring exists. Interpreter is the hardcoded JSONB predicate engine (NOT `eval`),
  per dev-spec §3.3 (locked).
- **D-08:** **Delivery targets are stored per-rule** — the chat_ids / group ids are entered in the
  rules builder (dev-spec "deliveries по каналам правила"). No staff-Telegram-linking subsystem in
  Phase 4 (that more-robust option was considered and deferred — see Deferred).
- **D-09:** Team alerts **reuse the Phase-3 client aiogram bot** (same bot token, same webhook,
  same `notify`/`deliveries` queue + token-bucket rate limiting). Team chats are just different
  chat_ids; no separate team bot/token.

### Purchase Requests team actions (flagship screen)
- **D-10:** In-scope action set, **all → `audit_log` (FR-11)**: status change, assign owner
  (`assigned_to`), add note (team-only internal note, not client-visible), and Contact Buyer.
- **D-11:** **Contact Buyer = deep-link to the buyer's Telegram** (`tg://` / `https://t.me` from
  the `clients` row) for a manual reply, and logs that contact was initiated to `audit_log`.
  This honors the locked product boundary ("managers reply manually in Telegram; the system only
  records status changes" — no offers-module). Record-only was considered and rejected.
- **D-12:** **Mockup buttons drive real status transitions** on the internal `RequestStatus`
  machine: opening the detail → `viewed`; Contact Buyer → `in_progress`; Mark as Processed →
  `closed`; plus an explicit status dropdown for `offer_sent` / `matched` / `cancelled`. Assign
  owner and add note are separate actions. Every transition writes `request_status_history`
  **and** `audit_log`, with server-side valid-transition enforcement.

### Claude's Discretion
- **Export** on the Purchase Requests table (mockup shows an Export button): format (CSV vs
  Excel) and scope left to research/planning.
- **SSE-vs-polling build priority:** SSE `/feed/stream` + 30 s polling fallback is locked
  (DEC-realtime-sse-not-websocket); whether to ship polling-first with SSE as a fast-follow
  (reasonable given UZEX signals arrive on a ~15-min beat) is a planning call.
- **Keyset pagination** by `(event_at, id)` for `/feed`, role-based screen/action gating
  (admin/analyst/trader/viewer per REQUIREMENTS), shadcn/ui component selection, dark-theme
  token wiring, and KPI-card data sources — standard implementation details for research/planning.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/ROADMAP.md` — Phase 4: Dashboard + Source Constructor (goal + the 5 success criteria;
  note the SC#5 cross-phase caveat in `<domain>` above)
- `.planning/REQUIREMENTS.md` — REQ-live-feed (FR-10), REQ-purchase-requests (FR-11),
  REQ-price-trends (FR-12), REQ-alerts (FR-14), REQ-bot-team (FR-16), REQ-source-builder (FR-22)

### Build spec (how we build)
- `docs/polymer-intelligence-dev-spec.md` §3.2 — REST API surface for the internal dashboard
  (`GET /feed` keyset-paginated, `GET·PATCH /requests`, `GET·PATCH /signals`, `GET /prices/series`,
  `GET·PATCH·POST /sources`, `GET /alerts` + `GET·POST·PATCH /alert-rules`); SSE `GET /feed/stream`
- `docs/polymer-intelligence-dev-spec.md` §3.3 — alert engine: `evaluate_alert_rules`, the JSONB
  hardcoded predicate interpreter (NOT eval), `alerts` dedupe_key, `deliveries` + `send_delivery`
  token-bucket rate limits (25 msg/s bot, 1 msg/s chat_id)
- `docs/polymer-intelligence-dev-spec.md` §2.5 — adapter architecture: add-source-from-admin,
  auto-form from `config_schema`, Test-before-enable
- `docs/polymer-intelligence-dev-spec.md` §6.1 — dashboard pages (`/`, `/requests`, `/signals`,
  `/offers`, `/prices`, `/sources` + add-source wizard, `/alerts`, `/admin/users`); SSE hook with reconnect/backoff

### Client TZ (priority over dev-spec on any conflict)
- `docs/polymer-intelligence-tz.md` — FR-10..FR-16, FR-22; §6.1.6 source-constructor acceptance
  (admin onboards site + channel with no developer; failed-test source cannot be enabled);
  §5 NFR feed/table API ≤500 ms at up to 1M signals

### Schema (locked, DDL v1.1)
- `docs/polymer-intelligence-db-architecture.md` — `v_live_feed`, `signals`, `requests` (+ `.ai`),
  `request_files`, `request_status_history`, `price_points`, `sources` (health fields,
  `last_test_ok_at`, `config_schema`), `alerts`, `alert_rules`, `deliveries`, `audit_log`, `clients`

### Mockups (UI contract — new screens beyond these are scope change)
- `docs/polymer-intelligence-ui-mockups.md` §3 (Surface B) — sidebar nav, dashboard home KPIs +
  panels, the high-fidelity **Purchase Requests master-detail** (§3.2), Price Trends, `/sources`
  add-source wizard, `/alerts` rules; §5 screen→data mapping; §6 design-derived constraints
- Mockup images: `docs/photo_2026-06-13 17.57.0{6,8,10}.jpeg` (mockups 1, 2, 3)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `dashboard/` scaffold — Next.js 16 (app router) with deps already chosen in `package.json`:
  `@tanstack/react-query`, `@tanstack/react-table`, `recharts`, `lucide-react`,
  `class-variance-authority` + `clsx` + `tailwind-merge` (shadcn/ui prerequisites). Currently
  only `app/login/page.tsx` + bare `app/layout.tsx`/`page.tsx` exist — **shadcn/ui is NOT yet
  installed** and the sidebar/shell must be built (D-03 wave 1).
- `dashboard/tailwind.config.ts` — design tokens live here; **no hardcoded hex** in components
  (REQ-nfr-security pattern carried from Phase 1).
- `backend/app/api/admin_sources.py` — already serves source-types / `config_schema` feed
  (`GET /admin/source-types`) and source health endpoints from Phase 2; the add-source wizard
  auto-form renders from this.
- `backend/app/api/auth.py` + `deps.py` — JWT auth + `require_role` guard (admin/analyst/trader/
  viewer) from Phase 1, for dashboard authz and role-based screen/action gating.
- `backend/app/api/telegram_webhook.py` + the Phase-3 aiogram bot, `notify` Celery queue, and
  `deliveries` plumbing — **reused for team alert delivery** (D-09).
- `backend/app/models/` — `requests.py` (`Request`, `RequestFile`, `RequestStatusHistory`, `Client`),
  `enums.py` (`RequestStatus`, `staff_role`), plus `signals`/`price_points`/`sources`/`alerts`/
  `audit_log` ORM models (schema locked); `v_live_feed` view for the feed.
- `backend/app/services/` — Phase-1 audit pattern (`db.flush()`, caller commits) for request actions;
  Phase-2 SourceAdapter registry + per-source health/isolation for the source constructor + Test runs.

### Established Patterns
- **TZ:** UTC in DB, Asia/Tashkent on display (`DEC-tz-handling`) — apply to feed/relative-time,
  request timeline, KPI "Updated N min ago".
- **Audit:** write to `audit_log` via `db.flush()` (caller commits), sharing the audited action's
  transaction — reuse for all D-10 request actions.
- **Source enable invariant:** `is_enabled = true ⇒ last_test_ok_at IS NOT NULL` (enforced at seed
  + service layer in Phase 2) — the wizard's enable gate must uphold this (D-04).
- **`no_code` flag (Phase 2):** `telegram_channel`/`llm_page`/`html_table`/`rss` are `no_code=True`
  (wizard-addable); `uzex_*`/`cbu_rates` are built-in specialized adapters.
- **Idempotent writes / dedupe_key:** alerts use `rule:{rule_id}:{entity}:{id}` (dev-spec §3.3).

### Integration Points
- SSE `GET /feed/stream` emits new ids; the dashboard SSE hook invalidates the TanStack Query
  feed query (30 s polling fallback). First real consumer of the streaming endpoint.
- `evaluate_alert_rules(signal_id | request_id)` is invoked after entity creation → `alerts` →
  `deliveries` → `send_delivery` on the existing bot/notify queue (D-09).
- Add-source Test runs the existing SourceAdapter `test()` for `html_table`/`rss` and returns
  ≤10 parsed signal-draft rows for preview (D-06).
</code_context>

<specifics>
## Specific Ideas

- The **Purchase Requests master-detail** is the highest-fidelity Phase-1 dashboard deliverable
  (PROJECT.md / mockups §6) — build it to mockup §3.2 fidelity (KPI cards, filter bar, paginated
  table, right detail panel with Request Details / Source Information / AI Analysis / Actions).
- AI sections must be **layout-final now, data-filled in Phase 5** — design them so Phase 5 is a
  data wire-up, not a redesign (D-01).
- `telegram_channel`/`llm_page` are **pre-stageable** in the wizard (config saved, "Pending
  activation (Phase 5)" badge) — admins can prepare them ahead of the engine landing (D-05).
- Contact Buyer is a **deep link, not an in-app messaging feature** — preserves the "managers
  reply manually in Telegram" boundary (D-11).
</specifics>

<deferred>
## Deferred Ideas

- **Staff Telegram linking subsystem** (staff `/start` the bot to register their chat_id; rules
  target staff by role/user) — considered for alert delivery; deferred in favor of per-rule
  chat_id config for the MVP (D-08). Revisit if per-rule chat_id entry proves error-prone.
- **Rule-based lead/hot-lead stub** (non-LLM heuristic to populate Hot Leads / scores before
  Phase 5) — considered and rejected in favor of honest placeholders (D-01); Phase 5 delivers
  real lead scoring.
- **`telegram_channel` + `llm_page` live Test/enable** (one-shot MTProto read; real LLM extraction
  Test) — deferred to Phase 5 where the userbot and LLM-extraction engines are built; Phase 4 only
  saves their config in a pending state (D-04).
- Otherwise discussion stayed within phase scope.

</deferred>

---

*Phase: 4-dashboard-source-constructor*
*Context gathered: 2026-06-17*
