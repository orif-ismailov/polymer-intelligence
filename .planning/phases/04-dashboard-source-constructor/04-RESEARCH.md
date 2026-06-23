# Phase 4: Dashboard + Source Constructor — Research

**Researched:** 2026-06-17
**Domain:** Next.js 16 app-router dashboard, FastAPI REST + SSE, TanStack Query/Table, shadcn/ui, JSONB alert interpreter, no-code adapter wizard
**Confidence:** HIGH (all findings grounded in existing codebase + canonical docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** AI-only elements render in their **final-shape layout with a graceful empty/placeholder state** ("AI analysis available after Phase 5" / "pending"). No hidden sections, no dead-end blank cards — Phase 5 just fills the data.
- **D-02:** The AI block's **Price Analysis line (target price vs. market average) IS computed for real in Phase 4** from `price_points`. Treat it as a non-AI field.
- **D-03:** **Foundation-first.** Wave 1 builds the shared dashboard shell — left sidebar nav, shadcn/ui setup (not yet installed), TanStack Query client, the SSE/polling refresh hook, and the auth-guarded app-router layout — then feature screens build in parallel waves on top.
- **D-04:** `html_table` + `rss` are **fully live in Phase 4**: wizard auto-form, real Test (live fetch + parse), preview, and enable-on-pass all work end-to-end. `telegram_channel` + `llm_page` are **wizard-configurable and saved, but their Test/enable are gated** until Phase 5. Invariant `is_enabled = true ⇒ last_test_ok_at IS NOT NULL` must hold.
- **D-05:** Pending types show a **"Pending activation (Phase 5)" badge** in the sources list with disabled Test/enable controls.
- **D-06:** Test preview renders **parsed signal drafts** — up to 10 normalized rows (product / grade / volume / price / currency / section / event_at), not raw pre-normalization rows.
- **D-07:** Rule builder exposes the full predicate set; `lead_score_gte` labeled "Activates with Phase 5 AI" (visible but disabled). Interpreter is the hardcoded JSONB engine, NOT `eval`.
- **D-08:** Delivery targets stored **per-rule** (chat_ids entered in the rules builder). No staff-Telegram-linking subsystem in Phase 4.
- **D-09:** Team alerts **reuse the Phase-3 client aiogram bot** (same token, same `notify`/`deliveries` queue, token-bucket rate limiting).
- **D-10:** In-scope action set on requests: status change, assign owner, add note, Contact Buyer — **all → `audit_log`**.
- **D-11:** Contact Buyer = `tg://` / `https://t.me` deep link from the `clients` row. Logs to `audit_log`. No in-app messaging.
- **D-12:** Mockup buttons drive real status transitions. Opening detail → `viewed`; Contact Buyer → `in_progress`; Mark as Processed → `closed`. Server-side valid-transition enforcement. Every transition writes `request_status_history` AND `audit_log`.
- **DEC-realtime-sse-not-websocket:** SSE `/feed/stream` + 30 s polling fallback. No WebSocket.
- **DEC-tz-handling:** UTC in DB, Asia/Tashkent on display.
- **Keyset pagination** by `(event_at, id)` for `/feed`.

### Claude's Discretion

- **Export** on the Purchase Requests table: format (CSV vs Excel) and scope. **Resolved in UI-SPEC:** CSV, current filtered result set (all columns), backend streams.
- **SSE-vs-polling build priority:** SSE `/feed/stream` + 30 s polling fallback is locked. Whether to ship polling-first with SSE as a fast-follow is a planning call.
- **shadcn/ui component selection**, dark-theme token wiring, KPI-card data sources — standard implementation details.

### Deferred Ideas (OUT OF SCOPE)

- Staff Telegram linking subsystem (staff `/start` the bot to register their chat_id)
- Rule-based lead/hot-lead stub (non-LLM heuristic to populate Hot Leads)
- `telegram_channel` + `llm_page` live Test/enable (Phase 5)
- `/reports` approve flow and `/counterparties` (Future Milestone)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-live-feed (FR-10) | Unified feed (`v_live_feed`) with filters (period, product, signal type, source, urgency); SSE + ≤30 s polling fallback; feed/table API ≤500 ms at up to 1M signals | `GET /feed` keyset pagination by `(event_at, id)` with composite index; SSE `GET /feed/stream`; TanStack Query `useQuery` + `invalidateQueries` on SSE message |
| REQ-purchase-requests (FR-11) | Requests table + detail card (details, files, AI block) + actions (status change, assign owner, notes); all → `audit_log` | All REST endpoints in `GET /requests`, `PATCH /requests/{id}`; detail panel (400px fixed); D-12 status machine; audit_service pattern already established |
| REQ-price-trends (FR-12) | Price chart per product/market from `price_points` | `GET /prices/series`; Recharts `LineChart`; downsampling in SQL (daily as-is, >1yr → weekly aggregate per dev-spec §3.1) |
| REQ-alerts (FR-14) | Alert feed + rules builder (product, volume/price threshold, urgency, channel) | `GET/POST/PATCH /alert-rules`; JSONB predicate interpreter (hardcoded, not eval); `alerts` + `deliveries` tables |
| REQ-bot-team (FR-16) | Alert delivery to DM/group per rules; Telegram rate limits via `deliveries` queue | Reuse Phase-3 `notify` Celery queue + `send_delivery` + token-bucket rate limit (25 msg/s bot, 1 msg/s chat_id) |
| REQ-source-builder (FR-22) | Admin wizard: pick type → auto-form from `config_schema` → Test with ≤10-row preview → enable. Enable impossible without passing test (TZ §6.1.6) | `GET /admin/source-types` already returns `config_schema`; `TestResult.sample_rows` already capped at 10 in `base.py`; `is_enabled ⇒ last_test_ok_at IS NOT NULL` invariant already enforced in Phase 2 |
</phase_requirements>

---

## Summary

Phase 4 is a large full-stack build on top of a solid Phase 1–3 foundation. The backend is missing all the dashboard REST APIs (`/feed`, `/requests`, `/signals`, `/prices/series`, `/sources`, `/alert-rules`) and the SSE endpoint — these must all be built from scratch in this phase. The frontend starts from a bare Next.js 16 scaffold (only `/login` page exists) and needs shadcn/ui installed, the shared shell (sidebar + layout), TanStack Query provider, and all six feature screens.

The highest-complexity items requiring careful planning are: (1) the SSE `EventSource` hook with exponential backoff reconnect and TanStack Query cache invalidation; (2) the no-code auto-form renderer that maps a Pydantic v2 `model_json_schema()` output to React form fields with validation; (3) the Test-before-enable flow enforcing `is_enabled = true ⇒ last_test_ok_at IS NOT NULL`; and (4) the keyset pagination query on `v_live_feed` that must stay ≤500 ms at 1M signals. Everything else (shadcn/ui setup, TanStack Table, Recharts, auth guard, JSONB interpreter, audit trail) follows established patterns that already exist in the codebase.

The wave decomposition is already decided (D-03: foundation-first): Wave 1 builds the shared shell; subsequent waves build feature screens in parallel. No adapters for `html_table`/`rss`/`telegram_channel`/`llm_page` exist yet — they are Phase 4 deliverables alongside their backend APIs and frontend wizard.

**Primary recommendation:** Build the API layer and SSE infrastructure first (Wave 1), then frontend shell (Wave 1 parallel), then feature screens in two parallel waves (Wave 2: feed + requests master-detail; Wave 3: prices + sources + alerts), then acceptance gate (Wave 4).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Live feed with filters + pagination | API / Backend | Browser / Client | Filtering/sorting at DB layer; client only paginates and renders |
| SSE real-time push | API / Backend | Browser / Client | Server emits `text/event-stream`; client hook calls `invalidateQueries` |
| Purchase Requests status machine | API / Backend | — | Valid-transition enforcement must be server-side (T-03-09 pattern) |
| Audit log writes | API / Backend | — | All writes go via `audit_service.write_audit()` in the same DB transaction |
| Price chart data (downsampling) | API / Backend | Browser / Client | SQL-level weekly aggregation for >1yr ranges; Recharts renders |
| Alert rule evaluation | API / Backend (Celery) | — | `evaluate_alert_rules()` runs post-entity-create, not in browser |
| Telegram alert delivery | API / Backend (Celery `notify`) | — | `send_delivery` task on the existing `notify` queue (D-09) |
| Auto-form from `config_schema` | Browser / Client | API / Backend | Frontend renders form; schema fetched from `GET /admin/source-types`; validation mirrors schema |
| Test-before-enable invariant | API / Backend | Browser / Client | Backend enforces `last_test_ok_at IS NOT NULL` before `is_enabled=true`; UI mirrors but does not gate |
| Role-based screen/action gating | API / Backend | Browser / Client | `require_role` dep is the security boundary; UI hides as UX convenience only |
| JWT auth guard | API / Backend | Browser / Client | Token decoded server-side; client redirects on 401 |
| Keyset pagination `(event_at, id)` | API / Backend | — | Composite index query; cursor passed as query params |
| Dark-theme token wiring | Browser / Client | — | CSS variables via shadcn/ui `components.json`; Tailwind config already has tokens |
| Price Analysis (target vs. market avg) | API / Backend | Browser / Client | Computed from `price_points` query; returned in request detail response |
| Contact Buyer deep-link | Browser / Client | — | `tg://` / `https://t.me` link built from `clients.telegram_user_id`; logs to audit via PATCH |

---

## Standard Stack

### Core (already installed — no new installation needed except shadcn/ui)

| Library | Current Version in package.json | Latest | Purpose | Status |
|---------|--------------------------------|--------|---------|--------|
| next | ^16.2.6 (latest: 16.2.9) | 16.2.9 | App router, RSC, standalone output | Already installed [VERIFIED: npm registry] |
| react | ^18.3.1 | 18.3.1 | UI framework | Already installed |
| @tanstack/react-query | ^5.51.1 (latest: 5.101.0) | 5.101.0 | Server state, polling, invalidation | Already installed [VERIFIED: npm registry] |
| @tanstack/react-table | ^8.19.3 (latest: 8.21.3) | 8.21.3 | Headless table engine | Already installed [VERIFIED: npm registry] |
| recharts | ^2.12.7 (latest: 3.8.1) | 3.8.1 | Price charts (LineChart) | Already installed [VERIFIED: npm registry] |
| lucide-react | ^0.408.0 (latest: 1.20.0) | 1.20.0 | Icons | Already installed [VERIFIED: npm registry] |
| class-variance-authority | ^0.7.0 | 0.7.1 | Component variant system (shadcn prereq) | Already installed [VERIFIED: npm registry] |
| clsx | ^2.1.1 | 2.1.1 | Class merging | Already installed [VERIFIED: npm registry] |
| tailwind-merge | ^2.4.0 | 2.4.0 | Tailwind class dedup | Already installed [VERIFIED: npm registry] |

**Note on version drift:** `recharts` in package.json is `^2.12.7` but latest is 3.8.1 (major version bump). `lucide-react` similarly drifted from `^0.408.0` to 1.20.0. `@tanstack/react-query` drifted from `^5.51.1` to 5.101.0. All are backwards-compatible minor/patch updates within their semver ranges; no breaking changes expected for the API surface used. [ASSUMED — based on semver guarantees; verify with changelog before upgrading]

### New in Phase 4

| Library | Install Command | Purpose | Note |
|---------|----------------|---------|------|
| shadcn/ui CLI | `npx shadcn@4.11.0 init` | Component library installer (not a runtime dep) | Writes `components.json` + CSS vars; see Pitfall 1 for dark-theme wiring |
| Radix UI primitives | Auto-installed by shadcn | Accessible headless components | Installed per-component by shadcn CLI; not directly depended on |

**shadcn components to add (one-time `npx shadcn add <name>`):** `button input select dialog alert-dialog table badge card tabs separator tooltip popover dropdown-menu sheet skeleton command calendar`

### Backend additions (Phase 4 builds these)

All backend APIs listed below need to be built in Phase 4. None exist yet.

| Module | File | Purpose |
|--------|------|---------|
| `GET /feed` + `GET /feed/stream` (SSE) | `backend/app/api/feed.py` | Unified live feed with keyset pagination and SSE |
| `GET /requests`, `PATCH /requests/{id}` | `backend/app/api/dashboard_requests.py` | Request table + detail + team actions |
| `GET /signals`, `PATCH /signals/{id}` | `backend/app/api/signals.py` | Signals table |
| `GET /prices/series` | `backend/app/api/prices.py` | Price chart data |
| `GET/PATCH/POST /sources` | `backend/app/api/sources.py` | Source list + enable/disable + add |
| `POST /sources/{id}/test` | `backend/app/api/sources.py` | Test-before-enable |
| `GET/POST/PATCH /alert-rules` | `backend/app/api/alert_rules.py` | Rules builder CRUD |
| `GET /alerts` | `backend/app/api/alert_rules.py` | Alert feed |
| `GET /admin/users` | `backend/app/api/admin_users.py` | Staff user list (admin-only) |
| `alert_service.evaluate_alert_rules` | `backend/app/services/alert_service.py` | JSONB predicate interpreter + delivery dispatch |
| Ingest adapters `html_table`, `rss`, `telegram_channel`, `llm_page` | `backend/app/ingest/{html_table,rss,telegram_channel,llm_page}/adapter.py` | No-code source adapters |

---

## Package Legitimacy Audit

> All packages in the Standard Stack are either already installed (from Phase 1–3) or installed via the shadcn CLI. The seam flagged several as `SUS` due to "too-new" (recent version publish date), but all have official repos and millions of weekly downloads. They are project-committed pre-Phase-4 packages.

| Package | Registry | Published | Downloads/wk | Source Repo | Verdict | Disposition |
|---------|----------|-----------|-------------|-------------|---------|-------------|
| next | npm | 2026-06-09 | 38.2M | github.com/vercel/next.js | SUS (too-new) | Pre-installed in package.json — approved. The `too-new` flag is a maintenance release of a 10yr-old framework. |
| @tanstack/react-query | npm | 2026-06-02 | 58.9M | github.com/TanStack/query | SUS (too-new) | Pre-installed — approved. Same reasoning. |
| @tanstack/react-table | npm | 2025-04-14 | 14.8M | github.com/TanStack/table | OK | Approved |
| recharts | npm | 2026-03-25 | 52.8M | github.com/recharts/recharts | OK | Approved |
| lucide-react | npm | 2026-06-16 | 86.4M | github.com/lucide-icons/lucide | SUS (too-new) | Pre-installed — approved |
| class-variance-authority | npm | 2024-11-26 | 53.6M | github.com/joe-bell/cva | OK | Approved |
| clsx | npm | 2024-04-23 | 103.9M | github.com/lukeed/clsx | OK | Approved |
| tailwind-merge | npm | 2026-05-10 | 70.7M | github.com/dcastil/tailwind-merge | OK | Approved |
| shadcn (CLI) | npm | 2026-06-08 | 5.6M | github.com/shadcn-ui/ui | SUS (too-new) | CLI installer from official shadcn-ui org — approved. Not a runtime dependency. |

**Packages removed due to SLOP verdict:** none

**Packages flagged as suspicious SUS:** All `SUS` flags are `too-new` (recent maintenance release, not a new project). All are from established, recognized organizations and are already committed to `package.json`. No `checkpoint:human-verify` blocks are required since no new third-party packages are being introduced to the project for the first time.

---

## Architecture Patterns

### System Architecture Diagram

```
Browser (Next.js App Router)
  │
  ├─ GET /api/v1/feed?cursor=...             → feed.py keyset query v_live_feed
  ├─ EventSource /api/v1/feed/stream         → feed.py SSE (new IDs only)
  │     └─ on message → invalidateQueries(['feed'])
  ├─ GET /api/v1/requests?...                → dashboard_requests.py
  ├─ PATCH /api/v1/requests/{id}             → status machine + audit_log
  ├─ GET /api/v1/prices/series               → prices.py (SQL downsample)
  ├─ GET /api/v1/sources                     → sources.py (health + config)
  ├─ POST /api/v1/sources/{id}/test          → sources.py → SourceAdapter.test()
  ├─ GET /api/v1/alerts                      → alert_rules.py
  └─ GET/POST/PATCH /api/v1/alert-rules      → alert_rules.py

                                 Celery `parse` queue
                                       │
                              evaluate_alert_rules(signal_id)
                                       │
                               alert_service.py
                               ├─ JSONB predicate match
                               ├─ alerts (dedupe_key ON CONFLICT)
                               └─ deliveries → send_delivery task
                                               │
                                         notify queue
                                               │
                                    aiogram bot → Telegram DM/group
                                    (same bot token as Phase 3)
```

### Recommended Project Structure

```
dashboard/
├── app/
│   ├── (dashboard)/          # Route group — auth-guarded layout
│   │   ├── layout.tsx        # Sidebar + QueryProvider + auth guard
│   │   ├── page.tsx          # / → Dashboard home
│   │   ├── requests/
│   │   │   └── page.tsx      # /requests — flagship master-detail
│   │   ├── signals/
│   │   │   └── page.tsx
│   │   ├── prices/
│   │   │   └── page.tsx
│   │   ├── sources/
│   │   │   └── page.tsx      # Sources list + wizard
│   │   ├── alerts/
│   │   │   └── page.tsx
│   │   └── admin/
│   │       └── users/
│   │           └── page.tsx
│   ├── login/
│   │   └── page.tsx          # Already exists
│   ├── layout.tsx            # Root layout (already exists, has dark class)
│   └── globals.css           # Already exists
├── components/
│   ├── ui/                   # shadcn-generated components (Button, Input, etc.)
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   └── AppShell.tsx
│   ├── feed/
│   │   ├── LiveFeedTable.tsx
│   │   └── FeedFilters.tsx
│   ├── requests/
│   │   ├── RequestsTable.tsx
│   │   ├── RequestDetailPanel.tsx
│   │   └── AiAnalysisBlock.tsx   # D-01/D-02 placeholder-aware
│   ├── sources/
│   │   ├── SourcesList.tsx
│   │   ├── AddSourceWizard.tsx
│   │   └── JsonSchemaForm.tsx    # Auto-form renderer
│   ├── alerts/
│   │   ├── AlertFeed.tsx
│   │   └── RuleBuilder.tsx
│   ├── prices/
│   │   └── PriceChart.tsx
│   └── shared/
│       ├── StatusChip.tsx
│       ├── UrgencyChip.tsx
│       └── KpiCard.tsx
├── hooks/
│   ├── useSSE.ts             # EventSource + backoff + fallback polling
│   └── useAuth.ts            # JWT read from memory/cookie
├── lib/
│   ├── api.ts                # fetch wrapper with Bearer token
│   ├── queryClient.ts        # TanStack QueryClient singleton
│   └── tz.ts                 # Asia/Tashkent display formatter
└── tailwind.config.ts        # Already has all tokens
```

```
backend/app/
├── api/
│   ├── feed.py               # NEW: GET /feed + GET /feed/stream (SSE)
│   ├── dashboard_requests.py # NEW: GET/PATCH /requests + note/assign
│   ├── signals.py            # NEW: GET/PATCH /signals
│   ├── prices.py             # NEW: GET /prices/series
│   ├── sources.py            # NEW: GET/PATCH/POST /sources + /test
│   ├── alert_rules.py        # NEW: alerts + alert-rules CRUD
│   ├── admin_users.py        # NEW: GET /admin/users
│   ├── admin_sources.py      # EXISTS: GET /admin/source-types
│   ├── auth.py               # EXISTS
│   └── deps.py               # EXISTS
├── services/
│   ├── alert_service.py      # NEW: evaluate_alert_rules + JSONB interpreter
│   ├── request_service.py    # EXISTS: add PATCH actions for Phase 4 (note, assign, contact)
│   └── ...                   # EXISTS: audit, signal, source_health, etc.
└── ingest/
    ├── html_table/           # NEW: HtmlTableAdapter
    ├── rss/                  # NEW: RssAdapter
    ├── telegram_channel/     # NEW: TelegramChannelAdapter (config-save only, no live fetch)
    └── llm_page/             # NEW: LlmPageAdapter (config-save only, no live fetch)
```

### Pattern 1: Keyset Pagination for `v_live_feed`

**What:** Cursor-based pagination using `(event_at, id)` that avoids OFFSET instability and stays ≤500 ms at 1M rows.

**When to use:** All list endpoints on `v_live_feed` and `requests` table.

```python
# Source: dev-spec §3.2 + DB architecture §4 index on (kind, event_at DESC)
# VERIFIED in codebase: signals has CREATE INDEX ON signals (kind, event_at DESC)

@router.get("/feed")
def get_feed(
    cursor_event_at: datetime | None = None,
    cursor_id: int | None = None,
    limit: int = Query(default=50, le=200),
    kind: str | None = None,
    product_id: int | None = None,
    # ... other filters
    db: Session = Depends(get_db),
    _: StaffUser = Depends(get_current_staff_user),
):
    # Keyset WHERE clause: (event_at, id) < (cursor_event_at, cursor_id)
    # Correct index usage requires: WHERE (event_at < :cursor_ea)
    #   OR (event_at = :cursor_ea AND id < :cursor_id)
    # This uses the composite index efficiently without OFFSET
    query = """
        SELECT id, origin, kind, product_id, grade_text, volume,
               price, currency, region, urgency, status, event_at
        FROM v_live_feed
        WHERE (:cursor_ea IS NULL OR
               event_at < :cursor_ea OR
               (event_at = :cursor_ea AND id < :cursor_id))
          AND (:kind IS NULL OR kind = :kind)
          AND (:product_id IS NULL OR product_id = :product_id)
        ORDER BY event_at DESC, id DESC
        LIMIT :limit
    """
```

**Index needed:** `v_live_feed` is a UNION ALL view — the underlying `signals` table already has `CREATE INDEX ON signals (kind, event_at DESC)`. The `requests` table has `CREATE INDEX ON requests (status, created_at DESC)`. The view does not support direct index creation; query planner will use the underlying table indexes.

### Pattern 2: SSE Hook with Exponential Backoff

**What:** Browser-side `EventSource` wrapper that reconnects with backoff and falls back to polling at 30 s.

**When to use:** The live feed stream. One instance per dashboard session.

```typescript
// Source: dev-spec §6.1 (SSE hook with reconnect/backoff)
// Pattern verified as the only realtime mechanism (DEC-realtime-sse-not-websocket)

export function useSSE(url: string, onMessage: (id: string) => void) {
  const retryRef = useRef(1000); // ms, doubles on each failure, cap at 30000

  useEffect(() => {
    let es: EventSource;
    let pollFallback: ReturnType<typeof setTimeout>;
    let mounted = true;

    function connect() {
      es = new EventSource(url, { withCredentials: true });

      es.onmessage = (evt) => {
        retryRef.current = 1000; // reset backoff on success
        clearTimeout(pollFallback);
        onMessage(evt.data); // data = new signal/request id
      };

      es.onerror = () => {
        es.close();
        if (!mounted) return;
        // Polling fallback: if SSE fails, poll every 30 s
        pollFallback = setTimeout(() => {
          onMessage('poll'); // signals caller to refetch
        }, 30_000);
        // Reconnect with backoff
        setTimeout(connect, Math.min(retryRef.current, 30_000));
        retryRef.current = Math.min(retryRef.current * 2, 30_000);
      };
    }

    connect();
    return () => {
      mounted = false;
      es?.close();
      clearTimeout(pollFallback);
    };
  }, [url]);
}
```

**TanStack Query integration:**
```typescript
// In the feed page component
const queryClient = useQueryClient();
useSSE('/api/v1/feed/stream', () => {
  queryClient.invalidateQueries({ queryKey: ['feed'] });
});
const { data } = useQuery({ queryKey: ['feed', filters], queryFn: fetchFeed });
```

**Backend SSE endpoint:**
```python
# Source: dev-spec §3.2 "GET /feed/stream (новые id)"
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio

@router.get("/feed/stream")
async def feed_stream(
    _: StaffUser = Depends(get_current_staff_user),
):
    async def event_generator():
        # Subscribe to a Redis pub/sub channel that receives new signal/request IDs
        # emitted by the parse/create tasks after each entity creation
        async with redis_pubsub.subscribe("feed:new") as sub:
            async for message in sub:
                yield f"data: {message}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

**Implementation note:** The SSE stream needs a Redis pub/sub channel (or a simpler in-memory asyncio queue). The existing Redis instance from Phase 1 docker-compose is available. [ASSUMED — Redis pub/sub as the SSE backend mechanism; the simpler alternative is periodic polling from the SSE handler itself using a long-poll loop checking for rows created after a watermark]

### Pattern 3: JSONB Predicate Interpreter (Alert Engine)

**What:** Hardcoded Python dict-based predicate evaluator — no `eval`, no dynamic code execution.

**When to use:** `evaluate_alert_rules(signal_id | request_id)` called after entity creation.

```python
# Source: dev-spec §3.3 JSONB predicate interpreter (hardcoded, NOT eval)
# condition JSONB example: {"kind": ["buy_request"], "product_id": [1,2],
#                            "volume_gte": 200, "urgency_in": ["high"],
#                            "lead_score_gte": 0.8, "source_kind": ["webapp"]}

def evaluate_condition(condition: dict, entity: Signal | Request) -> bool:
    """Hardcoded interpreter for Phase-1 predicate set. Never uses eval()."""

    # Each predicate returns True to continue matching, False to reject
    if "kind" in condition:
        if entity.kind not in condition["kind"]:
            return False

    if "product_id" in condition:
        if entity.product_id not in condition["product_id"]:
            return False

    if "volume_gte" in condition:
        if entity.volume is None or entity.volume < condition["volume_gte"]:
            return False

    if "urgency_in" in condition:
        urgency_val = entity.urgency.value if entity.urgency else None
        if urgency_val not in condition["urgency_in"]:
            return False

    if "source_kind" in condition:
        if entity.source_kind not in condition["source_kind"]:
            return False

    if "lead_score_gte" in condition:
        # Phase 4: lead_score is always None/absent — predicate never matches
        # This is correct: D-07 says rules can be authored, they just won't fire
        lead_score = (entity.ai or {}).get("lead_score")
        if lead_score is None or lead_score < condition["lead_score_gte"]:
            return False

    return True


def evaluate_alert_rules(
    db: Session,
    signal_id: int | None = None,
    request_id: int | None = None,
) -> None:
    """Evaluate all enabled rules against the newly created entity.
    On match: create alert with dedupe_key, create deliveries, enqueue send_delivery.
    dedupe_key = 'rule:{rule_id}:{entity}:{id}'
    """
    entity = _load_entity(db, signal_id, request_id)
    rules = db.query(AlertRule).filter(AlertRule.is_enabled == True).all()

    for rule in rules:
        if not evaluate_condition(rule.condition, entity):
            continue

        entity_type = "signal" if signal_id else "request"
        entity_id = signal_id or request_id
        dedupe_key = f"rule:{rule.id}:{entity_type}:{entity_id}"

        alert = Alert(
            kind=rule.kind,
            rule_id=rule.id,
            severity="info",
            title=f"Alert: {rule.name}",
            body=_format_body(entity),
            signal_id=signal_id,
            request_id=request_id,
            dedupe_key=dedupe_key,
        )
        db.add(alert)
        try:
            db.flush()  # get alert.id; ON CONFLICT(dedupe_key) fails here → skip
        except IntegrityError:
            db.rollback()  # duplicate — already alerted
            continue

        # Create deliveries for each channel in rule.channels
        for channel_config in rule.channels:
            delivery = Delivery(
                alert_id=alert.id,
                channel=channel_config["type"],
                recipient=str(channel_config["chat_id"]),
            )
            db.add(delivery)

        db.flush()
        # Enqueue the send_delivery task on the existing notify queue (D-09)
        send_delivery.apply_async(args=[alert.id], queue="notify")
```

### Pattern 4: Auto-Form from Pydantic v2 JSON Schema

**What:** React component that renders form fields from a `model_json_schema()` output.

**When to use:** Step 2 of the Add Source wizard (D-06).

```typescript
// Source: dev-spec §2.5 (auto-form from config_schema)
// GET /admin/source-types returns: [{ type_name, config_schema, no_code }]
// config_schema is a Pydantic v2 JSON Schema (RFC 8927 / JSON Schema draft 2020-12)

interface JsonSchemaProperty {
  type: 'string' | 'integer' | 'number' | 'boolean';
  title?: string;
  description?: string;
  format?: 'uri' | 'date-time';
  enum?: string[];
  default?: unknown;
}

interface ConfigSchema {
  properties: Record<string, JsonSchemaProperty>;
  required?: string[];
  title?: string;
}

function JsonSchemaForm({ schema, onSubmit }: {
  schema: ConfigSchema;
  onSubmit: (values: Record<string, unknown>) => void;
}) {
  const required = new Set(schema.required ?? []);

  return (
    <form onSubmit={...}>
      {Object.entries(schema.properties).map(([key, prop]) => {
        const isRequired = required.has(key);
        const label = prop.title ?? key;

        // URL fields get an SSRF hint
        if (prop.format === 'uri') {
          return <UrlField key={key} name={key} label={label} required={isRequired}
                           hint="Public URLs only." />;
        }
        // Enum → Select
        if (prop.enum) {
          return <SelectField key={key} name={key} label={label}
                              options={prop.enum} required={isRequired} />;
        }
        // Integer → number input
        if (prop.type === 'integer' || prop.type === 'number') {
          return <NumberField key={key} name={key} label={label} required={isRequired} />;
        }
        // Default: text input
        return <TextField key={key} name={key} label={label} required={isRequired}
                          description={prop.description} />;
      })}
      <Button type="submit">Continue</Button>
    </form>
  );
}
```

**Validation note:** Required field enforcement is checked client-side from `schema.required[]`. Do not rely on Pydantic's server-side error messages for user-facing validation in the wizard — mirror required checks in the form itself.

### Pattern 5: shadcn/ui Installation with Existing Tokens

**What:** Initialize shadcn/ui in the existing Next.js project without overwriting tailwind.config.ts.

**When to use:** Wave 1 step 1.

```bash
# Run inside dashboard/
# Invoke with explicit version to avoid SUS "too-new" flag uncertainty
npx shadcn@4.11.0 init
```

**During `shadcn init` prompts, choose:**
- Style: Default
- Base color: Slate (matches existing `bg-background: #0f172a` / slate-900 tokens)
- CSS variables: Yes (creates CSS vars in globals.css)

**Critical post-init step:** shadcn writes new CSS variables (e.g. `--background`, `--foreground`) to `globals.css`. These must be reconciled with the existing `tailwind.config.ts` tokens. The strategy is:

```css
/* In globals.css @layer base :root and .dark blocks — map shadcn vars to existing token values */
.dark {
  --background: 15 23 42;     /* #0f172a = bg-background (slate-900) */
  --foreground: 248 250 252;  /* #f8fafc = foreground.DEFAULT */
  --card: 30 41 59;           /* #1e293b = bg-background-secondary */
  --card-foreground: 248 250 252;
  --primary: 16 185 129;      /* #10b981 = accent (emerald-500) */
  --primary-foreground: 255 255 255;
  --muted: 51 65 85;          /* #334155 = bg-background-tertiary */
  --muted-foreground: 148 163 184; /* #94a3b8 = foreground-muted */
  --border: 51 65 85;         /* #334155 = border-DEFAULT */
  --ring: 16 185 129;         /* accent for focus ring */
  /* ... */
}
```

**Do NOT replace tailwind.config.ts token values** — shadcn's CSS variables are the bridge between shadcn components and the existing tokens. The `components.json` must set `tailwind.css` to `app/globals.css` and `tailwind.config` to `tailwind.config.ts`.

### Pattern 6: Test-Before-Enable Invariant

**What:** Backend enforces `is_enabled = true ⇒ last_test_ok_at IS NOT NULL` at PATCH time.

**When to use:** `PATCH /sources/{id}` with `is_enabled: true`.

```python
# Source: DB architecture §2 invariant; source_health_service.py pattern (Phase 2)
@router.patch("/sources/{source_id}")
def patch_source(
    source_id: int,
    body: SourcePatch,
    db: Session = Depends(get_db),
    _: StaffUser = Depends(require_admin),
):
    source = db.get(Source, source_id) or raise_404()

    if body.is_enabled is True and source.last_test_ok_at is None:
        raise HTTPException(
            status_code=422,
            detail="Source cannot be enabled until a test has passed successfully."
        )

    # Update fields
    if body.is_enabled is not None:
        source.is_enabled = body.is_enabled
    # ... other patchable fields
    db.commit()
```

**After a successful Test run:**
```python
# POST /sources/{id}/test
async def test_source(source_id: int, ...):
    adapter = get_adapter(source.adapter)
    result: TestResult = await adapter.test(source.config)

    if result.ok:
        # Update last_test_ok_at — now enable is possible
        source.last_test_ok_at = datetime.datetime.now(tz=datetime.UTC)
        db.commit()

    return {"ok": result.ok, "sample_rows": result.sample_rows, "error": result.error}
```

### Pattern 7: D-02 Price Analysis (Target vs. Market Average)

**What:** Compute target price vs. market average from `price_points` in the request detail response. This is a real Phase-4 computation, not AI-dependent.

```python
# In GET /requests/{id} response, include price_analysis inline
def compute_price_analysis(
    db: Session,
    product_id: int,
    target_price: Decimal | None,
    currency: str,
) -> dict | None:
    if target_price is None:
        return None

    # Get most recent price_points avg for this product
    row = db.execute(sa.text("""
        SELECT price_avg, currency
        FROM price_points
        WHERE product_id = :pid AND market = 'UZ'
        ORDER BY observed_on DESC
        LIMIT 1
    """), {"pid": product_id}).fetchone()

    if not row:
        return None

    market_avg = row[0]
    # Delta: positive = buyer wants higher than market (favorable for sellers)
    delta_pct = float((target_price - market_avg) / market_avg * 100)
    return {
        "target_price": float(target_price),
        "market_avg": float(market_avg),
        "delta_pct": round(delta_pct, 1),
        "label": f"{abs(delta_pct):.1f}% {'above' if delta_pct > 0 else 'below'} market average",
    }
```

### Pattern 8: AI Block Layout Contract (D-01)

**What:** Phase-5-safe AI block that renders placeholder state now without dead cards.

```tsx
// The AI block always renders with its final shape.
// In Phase 4: match_score = null → empty bar, recommendation = null → placeholder text.
// In Phase 5: fields populated → same layout, no redesign needed.

function AiAnalysisBlock({ ai, priceAnalysis }: {
  ai: { match_score?: number | null; demand_level?: string | null; recommendation?: string | null } | null;
  priceAnalysis: { delta_pct: number; label: string } | null;
}) {
  return (
    <section>
      <h3>AI Analysis</h3>

      {/* Match Score — placeholder in Phase 4 */}
      <div>
        <label>Match Score</label>
        <div className="h-2 rounded-full bg-background-tertiary overflow-hidden">
          <div
            className="h-full bg-accent transition-all"
            style={{ width: ai?.match_score != null ? `${ai.match_score * 100}%` : '0%' }}
          />
        </div>
        <span>{ai?.match_score != null ? `${Math.round(ai.match_score * 100)}%` : '—'}</span>
      </div>

      {/* Price Analysis — REAL in Phase 4 (D-02) */}
      {priceAnalysis ? (
        <div>
          <label>Price Analysis</label>
          <span className={priceAnalysis.delta_pct > 0 ? 'text-accent' : 'text-urgency-medium'}>
            {priceAnalysis.label}
          </span>
        </div>
      ) : (
        <div><label>Price Analysis</label><span className="text-foreground-subtle">No price data available</span></div>
      )}

      {/* Demand Level — placeholder in Phase 4 */}
      <div>
        <label>Demand Level</label>
        <span>{ai?.demand_level ?? <span className="text-foreground-subtle italic">Pending (Phase 5)</span>}</span>
      </div>

      {/* Recommendation — placeholder in Phase 4 */}
      <div>
        <label>Recommendation</label>
        <p className="text-foreground-subtle italic">
          {ai?.recommendation ?? 'AI analysis available after Phase 5'}
        </p>
      </div>
    </section>
  );
}
```

### Anti-Patterns to Avoid

- **Do not put `is_enabled=true` validation only in UI:** The `PATCH /sources/{id}` endpoint must enforce the invariant server-side. The UI gate is UX-only (disable the button until test passes).
- **Do not use OFFSET pagination on `v_live_feed`:** At 1M rows, `OFFSET 50000` is a full scan. Use keyset `(event_at, id)` cursor only.
- **Do not eval() or interpret alert rule JSONB as code:** The Phase-1 predicate set is hardcoded per-key in Python. No dynamic evaluation.
- **Do not use WebSocket for the live feed:** DEC-realtime-sse-not-websocket is locked. EventSource only.
- **Do not hardcode hex values in components:** All colors via Tailwind token classes only (REQ-nfr-security pattern from STATE.md).
- **Do not overwrite tailwind.config.ts during shadcn init:** The file has locked design tokens. shadcn CSS variables must be reconciled to the existing values, not replaced.
- **Do not call `db.commit()` in service functions:** The existing audit_service pattern (`db.flush()`, caller commits) must be followed for all Phase-4 services. Violation breaks the shared-transaction audit guarantee.
- **Do not use `no_code=False` adapters in the wizard:** `uzex_*` and `cbu_rates` are built-in; the wizard only shows `no_code=True` types. The `_is_no_code()` helper in `admin_sources.py` already implements this.
- **Do not dispatch `send_delivery` with a `request_id` that has no `clients` row:** The `clients.telegram_user_id` lookup for Contact Buyer must handle NULL gracefully (buyer may have submitted via the public landing form, not the Telegram Web App).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Table with sorting/pagination | Custom table component | TanStack Table v8 (already installed) | Handles virtual rows, sticky headers, column sizing — 1-day DIY turns into 2 weeks |
| Line charts with responsive resize | Custom SVG chart | Recharts `LineChart` + `ResponsiveContainer` (already installed) | Handles tick formatting, legend, tooltip, responsive resize |
| Accessible dialog/sheet/tooltip | Custom modal | shadcn `Dialog`, `Sheet`, `Tooltip` (via shadcn init) | Radix handles focus trap, scroll lock, ARIA; building this correctly takes days |
| Token-bucket rate limiting for Telegram | Custom rate limiter | Existing `deliveries` queue + token-bucket in `send_delivery` task (Phase 3) | The global 25 msg/s and per-chat 1 msg/s limiters already exist (D-09) |
| Date/time formatting in Asia/Tashkent | `new Date().toLocaleString()` | `Intl.DateTimeFormat` with `timeZone: 'Asia/Tashkent'` (or backend-side ISO8601 string with tz offset) | Browser locale may differ from Asia/Tashkent; use explicit `Intl.DateTimeFormat` |
| Keyset cursor encoding | Manual string concatenation | Pass `cursor_event_at` + `cursor_id` as separate URL query params | Separate params are type-safe and debuggable; base64 cursor is opaque and harder to test |
| Pydantic JSON schema → form validation | Re-parse schema at runtime with custom logic | Mirror `schema.required[]` in client-side required checks | Pydantic schema is the source of truth; just read `required[]` array, don't re-infer |
| Telegram deep-link construction | Custom URL builder | `tg://user?id={telegram_user_id}` or `https://t.me/{telegram_user_id}` from `clients.telegram_user_id` | Standard Telegram deep-link formats |

**Key insight:** The codebase already has the hard parts (status machine, audit service, source adapter registry, token-bucket rate limiter). Phase 4 assembles them into APIs and a UI — avoid re-implementing any of these from scratch.

---

## Common Pitfalls

### Pitfall 1: shadcn CSS variables conflict with tailwind tokens

**What goes wrong:** Running `npx shadcn init` writes `--background: 0 0% 100%` (white) and `--foreground: 0 0% 3.9%` (near-black) to `globals.css` as light-theme defaults. The components then use `hsl(var(--background))` — which overrides the slate-900 dark background set by `tailwind.config.ts`.

**Why it happens:** shadcn writes CSS variables keyed to its own design system defaults; the Tailwind utility class `bg-background` resolves to `tailwind.config.ts` → `#0f172a`, but shadcn's component internals use `bg-background` which it defines as `hsl(var(--background))`. If the CSS var is light, the component renders light despite the Tailwind token.

**How to avoid:** After `shadcn init`, immediately reconcile the generated CSS variables in `globals.css` to match the existing Tailwind token values (see Pattern 5). The `html.dark` class is already set in `app/layout.tsx` — ensure the `.dark` block in globals.css has the correct dark values.

**Warning signs:** shadcn `Dialog` or `Card` renders white/light inside an otherwise dark page.

### Pitfall 2: `v_live_feed` UNION ALL does not have its own index

**What goes wrong:** Filtering `v_live_feed` by `product_id` with an added `WHERE product_id = :pid` clause causes a full scan of both `signals` and `requests` because the planner cannot push the predicate through the UNION ALL efficiently with a single composite index.

**Why it happens:** `v_live_feed` is defined as `SELECT ... FROM signals UNION ALL SELECT ... FROM requests`. Each branch is a separate table with separate indexes. The planner optimizes each branch independently, but only if the WHERE clause can be pushed into each branch.

**How to avoid:** Always filter with explicit WHERE clauses that reference indexed columns. `event_at` has an index on `signals (kind, event_at DESC)` and `requests (status, created_at DESC)`. For `product_id` filtering, verify the query plan with `EXPLAIN ANALYZE` and add a dedicated index (`CREATE INDEX ON signals (product_id, event_at DESC)` — already exists per DB architecture doc). [VERIFIED: DB architecture §4 shows `CREATE INDEX ON signals (product_id, event_at DESC)`]

**Warning signs:** `EXPLAIN` shows `Seq Scan` on `signals` for filtered feed queries.

### Pitfall 3: SSE response buffered by nginx

**What goes wrong:** SSE events are delivered in batches after a delay rather than immediately. The "● Live Data" indicator appears connected but events arrive 30–60 s late.

**Why it happens:** nginx's `proxy_buffering` defaults to `on`, which buffers the upstream SSE stream. The response body accumulates in nginx's buffer before forwarding.

**How to avoid:** Add `X-Accel-Buffering: no` header to the SSE response (shown in Pattern 2) and ensure the nginx config for the API proxy has `proxy_buffering off` for the `/api/v1/feed/stream` location.

**Warning signs:** Events arrive in bursts rather than individually; nginx access logs show the connection staying open but client receives nothing for seconds.

### Pitfall 4: Auto-form breaks on Pydantic Optional fields

**What goes wrong:** The JSON schema for a Pydantic model with `Optional[str]` fields contains `"anyOf": [{"type": "string"}, {"type": "null"}]` instead of `"type": "string"`. The simple auto-form renderer that checks `prop.type === 'string'` fails silently for optional fields.

**Why it happens:** Pydantic v2 `model_json_schema()` represents `Optional[X]` as `anyOf: [X, null]`. This is standard JSON Schema but requires the form renderer to unwrap `anyOf` arrays.

**How to avoid:** In the `JsonSchemaForm` renderer, normalize optional fields before rendering:
```typescript
function resolveType(prop: JsonSchemaProperty): JsonSchemaProperty {
  // Unwrap anyOf: [T, null] → T
  if ('anyOf' in prop) {
    const nonNull = (prop as any).anyOf.find((s: any) => s.type !== 'null');
    return nonNull ?? prop;
  }
  return prop;
}
```

**Warning signs:** Optional config fields (e.g. CSS selector in `html_table` adapter) don't render in the wizard form.

### Pitfall 5: Status machine allows `new → closed` via PATCH

**What goes wrong:** The `PATCH /requests/{id}` endpoint accepts any `status` value from the request body and updates without validating transitions. An analyst accidentally marks a `new` request as `closed`, bypassing `viewed` → `in_progress`.

**Why it happens:** The `VALID_TRANSITIONS` dict already exists in `request_service.py` from Phase 3 but the Phase-4 PATCH endpoint must call `transition_status()` rather than directly setting `request.status = body.status`.

**How to avoid:** The Phase-4 `PATCH /requests/{id}` router must call `request_service.transition_status(db, request, new_status, changed_by=current_user.id)` — the same function used by the Phase-3 webapp API. Never bypass it.

**Warning signs:** `request_status_history` rows show transitions that skip intermediate states.

### Pitfall 6: Contact Buyer logs audit but `clients.telegram_user_id` may be NULL

**What goes wrong:** The Contact Buyer action tries to build `tg://user?id={telegram_user_id}` but crashes or returns an empty link when the buyer submitted via the public landing form (which creates a `requests` row without a `clients.telegram_user_id`).

**Why it happens:** Phase 3 `clients.telegram_user_id` is nullable (BigInteger, nullable=True). Non-Telegram buyers don't have a Telegram ID.

**How to avoid:** The detail panel API response must include a `contact_available: bool` field derived from `clients.telegram_user_id IS NOT NULL`. The UI renders "Contact Buyer" as disabled with tooltip "No Telegram ID on file" when `contact_available = false`.

**Warning signs:** "Contact Buyer" button renders but clicking it opens `tg://user?id=None`.

### Pitfall 7: Token-bucket rate limit not applied to team alert deliveries

**What goes wrong:** Multiple alert rules fire simultaneously (e.g. a large UZEX batch creates 50 signals), each creating a delivery record, but `send_delivery` tasks are dispatched without the rate limiter, causing Telegram to return 429 errors and deliveries to fail.

**Why it happens:** The Phase-3 `send_delivery` task includes the token-bucket logic, but only if all team alerts use the same `notify` Celery queue (D-09). If a new `alert_delivery` queue is created separately, it bypasses the rate limiter.

**How to avoid:** All `send_delivery.apply_async()` calls from `evaluate_alert_rules` must go to the existing `notify` queue. The token-bucket rate limit (25 msg/s global bot, 1 msg/s per chat_id) is implemented in `send_delivery` — don't bypass it with a separate task.

---

## State of the Art

| Topic | Approach | Note |
|-------|----------|------|
| SSE in Next.js App Router | Client component with `useEffect` + `EventSource` (no `use server`) | SSE is a browser API — must run in a `"use client"` component. Route handlers can serve SSE but client must consume via `EventSource`, not `fetch`. [ASSUMED] |
| TanStack Query v5 API | `useQuery`, `useQueryClient`, `invalidateQueries` | v5 changed `invalidateQueries` to accept an options object: `{ queryKey: ['feed'] }`. The `^5.51.1` in package.json uses this API. [VERIFIED: npm registry] |
| Recharts v2 vs v3 | v2 stable (in package.json); v3 is latest | v3 released 2026-03 — breaking changes in component API. Stay on v2.x (`^2.12.7`) since it's already installed and tested. Upgrade is a separate planning item. [ASSUMED] |
| shadcn `Sheet` vs custom panel | Use `Sheet` for the right detail panel (400px) | `Sheet` component from shadcn provides the slide-in from right behavior with focus trap. The `side="right"` prop gives the correct animation. UI-SPEC specifies `role="dialog"` with `aria-labelledby`. [ASSUMED] |
| Keyset vs cursor-based pagination | Two separate query params (`cursor_event_at` + `cursor_id`) | More debuggable than opaque base64. The pair `(event_at, id)` forms a stable total order at 1M rows when the index on `signals(product_id, event_at DESC)` is used. [VERIFIED: DB architecture] |

**Deprecated/outdated:**
- OFFSET pagination on `v_live_feed`: Do not use. Performance degrades linearly with page number at 1M rows.
- `WebSocket` for realtime feed: Explicitly rejected by DEC-realtime-sse-not-websocket.
- `eval()` in alert rule interpreter: Never use. JSONB predicate interpreter is hardcoded per dev-spec §3.3.

---

## Runtime State Inventory

> This is a greenfield feature phase (building new screens and APIs on top of existing Phase 1–3 backend). It is not a rename/refactor/migration phase. Formal Runtime State Inventory is not required.

**Relevant state to be aware of:**
- `sources` table: Phase-2 seed populated `uzex_offers`, `uzex_contracts`, `uzex_deals`, `cbu_rates` with `is_enabled=true` and `last_test_ok_at` set. These will appear in the Phase-4 sources list. `no_code=False` for these types — wizard does not show them as addable.
- `signals` table: Real UZEX signals exist from Phase 2 testing. The live feed will show them on first load.
- `requests` table: Real requests exist from Phase 3. The Purchase Requests screen will show them.
- `alert_rules` / `alerts`: Empty at Phase 4 start. Seeding test data is needed for development.
- JWT tokens: Phase-1 auth infrastructure is live. Dashboard `/login` page exists but the `handleSubmit` TODO needs implementing (Phase-4 Wave 1 task).

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Dashboard build | ✓ | v24.11.1 | — |
| Python | Backend | ✓ | 3.14.3 | — |
| npm | Package install | ✓ | 11.6.2 | — |
| PostgreSQL (docker) | All backend APIs | ✓ (via docker-compose) | 16 | — |
| Redis (docker) | SSE pub/sub + Celery | ✓ (via docker-compose) | Present | — |
| shadcn CLI | Wave 1 setup | Will be fetched via `npx shadcn@4.11.0 init` | 4.11.0 | — |
| selectolax | html_table adapter | ✓ (installed in Phase 2) | Present | — |
| feedparser (RSS) | rss adapter | Not yet installed [ASSUMED] | — | httpx + xml.etree.ElementTree (stdlib) |
| aiogram | Telegram delivery | ✓ (Phase-3 installed) | Present | — |

**Missing dependencies with no fallback:** None that block execution.

**Missing dependencies with fallback:**
- `feedparser` for the RSS adapter: stdlib `xml.etree.ElementTree` can parse RSS/Atom; `feedparser` is more robust but not required. Planner should add `pip install feedparser` to the rss adapter task. [ASSUMED — feedparser not confirmed installed]

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest 8.2+ (confirmed in pyproject.toml) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd backend && pytest tests/ -x -q --tb=short` |
| Full suite command | `cd backend && pytest tests/ --tb=short` |
| Frontend typecheck | `cd dashboard && npm run typecheck` |
| Frontend lint | `cd dashboard && npm run lint` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-live-feed | `GET /feed` keyset pagination returns ≤500 ms, filters work, cursor advances | unit (mock DB) | `pytest tests/test_feed_api.py -x` | ❌ Wave 0 |
| REQ-live-feed | SSE endpoint emits `text/event-stream` and new entity IDs | unit (httpx TestClient async) | `pytest tests/test_feed_sse.py -x` | ❌ Wave 0 |
| REQ-purchase-requests | Status machine: `new→viewed` auto on detail open, invalid transition rejected | unit | `pytest tests/test_dashboard_requests.py -x` | ❌ Wave 0 |
| REQ-purchase-requests | All team actions write `audit_log` (status, note, assign, contact) | unit | `pytest tests/test_dashboard_requests.py::test_audit_trail -x` | ❌ Wave 0 |
| REQ-purchase-requests | D-02 price analysis computed from `price_points` | unit | `pytest tests/test_price_analysis.py -x` | ❌ Wave 0 |
| REQ-price-trends | `GET /prices/series` returns correct date range + downsampling | unit | `pytest tests/test_prices_api.py -x` | ❌ Wave 0 |
| REQ-alerts | JSONB interpreter: matching + non-matching predicates, `lead_score_gte` never matches in Phase 4 | unit (90%+ coverage per dev-spec §8) | `pytest tests/test_alert_service.py -x` | ❌ Wave 0 |
| REQ-alerts | Alert dedupe: same rule+entity creates one alert with `ON CONFLICT DO NOTHING` | unit | `pytest tests/test_alert_service.py::test_dedupe -x` | ❌ Wave 0 |
| REQ-bot-team | Delivery dispatched to `notify` queue with correct `chat_id` from rule.channels | unit (mock Celery) | `pytest tests/test_alert_service.py::test_delivery_dispatch -x` | ❌ Wave 0 |
| REQ-source-builder | `POST /sources/{id}/test` for `html_table` returns ≤10 parsed signal drafts | unit (httpx fixture) | `pytest tests/test_source_wizard.py::test_html_table_test -x` | ❌ Wave 0 |
| REQ-source-builder | `PATCH /sources/{id}` with `is_enabled=true` without test → 422 | unit | `pytest tests/test_source_wizard.py::test_enable_gate -x` | ❌ Wave 0 |
| REQ-source-builder | `telegram_channel` wizard save → `is_enabled=false`, `last_test_ok_at=NULL` | unit | `pytest tests/test_source_wizard.py::test_pending_source -x` | ❌ Wave 0 |
| REQ-nfr-performance | Feed API ≤500 ms at 1M simulated rows | integration (Postgres) | `pytest tests/test_feed_performance.py -x -m performance` (skip in CI if no DB) | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_feed_api.py tests/test_alert_service.py tests/test_source_wizard.py tests/test_dashboard_requests.py -x -q`
- **Per wave merge:** `cd backend && pytest tests/ -q && cd ../dashboard && npm run typecheck && npm run lint`
- **Phase gate:** Full backend suite green + `npm run typecheck` passes before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/test_feed_api.py` — covers REQ-live-feed (keyset pagination, filters, SSE)
- [ ] `backend/tests/test_feed_sse.py` — covers SSE event emission
- [ ] `backend/tests/test_dashboard_requests.py` — covers REQ-purchase-requests (status machine, audit)
- [ ] `backend/tests/test_price_analysis.py` — covers D-02 price analysis computation
- [ ] `backend/tests/test_prices_api.py` — covers REQ-price-trends
- [ ] `backend/tests/test_alert_service.py` — covers REQ-alerts + REQ-bot-team (JSONB interpreter, dedupe, delivery dispatch) — **dev-spec §8 mandates 90%+ coverage for the alert interpreter**
- [ ] `backend/tests/test_source_wizard.py` — covers REQ-source-builder (test endpoint, enable gate, pending state)
- [ ] `backend/tests/test_html_table_adapter.py` — covers html_table adapter fetch+test
- [ ] `backend/tests/test_rss_adapter.py` — covers rss adapter fetch+test

Existing tests to reuse as patterns:
- `tests/test_request_service.py` — mock DB pattern for testing state machines
- `tests/test_admin_source_types.py` — TestClient pattern for admin-only endpoints
- `tests/test_source_health.py` — invariant enforcement test pattern

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | JWT Bearer (`require_role` dep from Phase 1) |
| V3 Session Management | yes | Existing httpOnly refresh cookie pattern from Phase 1 |
| V4 Access Control | yes | `require_role`, `require_admin` deps — already enforced at API layer; UI hides as UX convenience only |
| V5 Input Validation | yes | Pydantic request models for all PATCH/POST bodies; `config_schema` validated against adapter Pydantic model |
| V6 Cryptography | no | No new cryptographic operations in Phase 4 |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR on `GET /requests/{id}` — analyst reads another user's private request | Tampering | Not applicable — requests are internal team data, not per-user private. All staff with required role can view. |
| Unauthorized `PATCH /requests/{id}` status change | Tampering/Elevation | `require_role(StaffRole.admin, StaffRole.analyst, StaffRole.trader)` on the endpoint; `viewer` role gets 403 |
| SSRF via `config_schema` URL field in Add Source wizard | Tampering | The existing `is_safe_url()` in `http_client.py` (Phase 2, DEC-ssrf-dns-resolution) must be called inside `html_table` and `rss` adapter `test()` methods before any HTTP fetch |
| Injection via `condition` JSONB in alert rules | Tampering | Hardcoded predicate interpreter (Pattern 3) — condition keys are checked against a known set, values are passed to ORM queries as bound parameters, never interpolated into SQL |
| Alert storm: one large batch triggering thousands of deliveries | Denial of Service | `deliveries` table + `send_delivery` token-bucket rate limiter (25 msg/s global, 1 msg/s per chat) already implemented in Phase 3 notify queue |
| Unauthorized source enable via frontend bypass | Tampering | Backend invariant check: `PATCH /sources/{id}` with `is_enabled=true` requires `last_test_ok_at IS NOT NULL` server-side (Pattern 6) |
| JWT role escalation via modified payload | Spoofing/Elevation | `require_role` reads role from verified JWT payload (DEC-auth-split); changing the claim would invalidate the signature |
| XSS via `body` or `title` fields in alerts rendered as HTML | Tampering | All text fields rendered as `text` in JSX (React escapes by default); do not use `dangerouslySetInnerHTML` anywhere in the dashboard |

---

## Sources

### Primary (MEDIUM confidence — codebase is the authoritative source)

- `docs/polymer-intelligence-dev-spec.md` §2.5, §3.2, §3.3, §6.1 — adapter architecture, REST API surface, alert engine, dashboard pages
- `docs/polymer-intelligence-db-architecture.md` §2–§9 — all table schemas, indexes, `v_live_feed` definition, invariants
- `docs/polymer-intelligence-tz.md` FR-10..FR-16, FR-22, §5 NFR, §6.1.6 — requirements and acceptance criteria
- `docs/polymer-intelligence-ui-mockups.md` §3, §5, §6 — screen specs, data mapping, design constraints
- `.planning/phases/04-dashboard-source-constructor/04-CONTEXT.md` — locked decisions D-01..D-12
- `.planning/phases/04-dashboard-source-constructor/04-UI-SPEC.md` — full UI design contract

### Secondary (codebase verified patterns)

- `backend/app/ingest/base.py` — `SourceAdapter` Protocol, `TestResult` (10-row cap verified)
- `backend/app/ingest/registry.py` — adapter self-registration pattern
- `backend/app/ingest/uzex/adapters.py` — concrete adapter example with `config_schema`
- `backend/app/api/admin_sources.py` — `GET /admin/source-types` already serving config_schema
- `backend/app/api/deps.py` — `require_role`, `require_admin`, `get_current_staff_user`
- `backend/app/services/audit_service.py` — `write_audit()` + `db.flush()` pattern
- `backend/app/services/request_service.py` — `VALID_TRANSITIONS`, `transition_status()`
- `backend/app/services/source_health_service.py` — `db.flush()` pattern, failure isolation
- `backend/app/models/requests.py` — `Request`, `RequestStatusHistory`, `Client`
- `backend/app/models/alerts.py` — `AlertRule`, `Alert`, `Delivery`
- `dashboard/tailwind.config.ts` — design tokens (verified all tokens match UI-SPEC)
- `dashboard/app/layout.tsx` — `html.dark` class set (shadcn dark mode prerequisite)
- `dashboard/app/login/page.tsx` — existing component pattern (Tailwind tokens, no hardcoded hex)
- `dashboard/package.json` — exact versions of all pre-installed dependencies

### Tertiary (LOW confidence — training knowledge, not verified in this session)

- SSE reconnect/backoff pattern in React (Pattern 2) [ASSUMED]
- `feedparser` package availability [ASSUMED]
- Recharts v2→v3 breaking changes [ASSUMED]
- shadcn CLI `--version 4.11.0` flag syntax [ASSUMED]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Redis pub/sub is the right mechanism for SSE event distribution (backend emits to `feed:new` channel, SSE handler subscribes) | Pattern 2 | If Redis pub/sub is unavailable or asyncio-incompatible with the current Redis library version, the simpler alternative is a periodic poll in the SSE handler (checking `signals.created_at > watermark`) — slower but no pub/sub dependency |
| A2 | `feedparser` is not yet installed in the backend venv | Environment Availability | If it is installed, the rss adapter task can use it directly without a `pip install` step |
| A3 | Recharts v2 (`^2.12.7`) API is compatible with the Phase-4 chart requirements — no breaking changes affect `LineChart`, `ResponsiveContainer`, `XAxis`, `YAxis` | Standard Stack | If Recharts v2 has a bug in `ResponsiveContainer` (known historical issue), the fix is `width="99%"` on `ResponsiveContainer` |
| A4 | The existing `send_delivery` Celery task (Phase 3) accepts both `telegram_dm` and `telegram_channel` delivery channel types and dispatches to the correct chat_id | Pattern 3 / D-09 | If `send_delivery` only handles client-notification templates (not generic alert delivery), a new path in `send_delivery` must be added for team alert messages |
| A5 | `npx shadcn@4.11.0 init` syntax is correct for the current shadcn CLI | Pattern 5 | If the pinned version flag is different (e.g. `npx shadcn-ui@...`), the seam SUS flag for "too-new" should prompt a checkpoint to verify the exact CLI invocation against official docs before running |
| A6 | `v_live_feed` query planner correctly uses `signals(product_id, event_at DESC)` index for product-filtered keyset queries | Pitfall 2 | If the planner falls back to Seq Scan for the UNION ALL view, add a covering index and restructure the query to use explicit CTEs |

---

## Open Questions

1. **SSE backend implementation: Redis pub/sub vs. periodic poll**
   - What we know: The SSE endpoint must emit new signal/request IDs. Redis is available. The aiogram bot already uses Redis.
   - What's unclear: Whether the existing Redis client library (likely `redis-py` async) is already installed and compatible with the FastAPI async context.
   - Recommendation: Check `backend/pyproject.toml` for `redis` or `aioredis` dependency. If present, use pub/sub. Otherwise, implement as a long-polling SSE handler that queries `signals WHERE created_at > :watermark ORDER BY created_at DESC LIMIT 100` every 2 s — simpler, no pub/sub channel management.

2. **`send_delivery` Phase-3 coverage for team alerts**
   - What we know: Phase-3 built `send_delivery` for client status notifications. D-09 says team alerts reuse the same queue.
   - What's unclear: Whether `send_delivery` has generic alert delivery logic or only client-template logic.
   - Recommendation: Read `backend/app/tasks/notify.py` (or equivalent) at planning time. If only client templates exist, the `send_delivery` task needs a new code path for `delivery_channel=telegram_dm` with the alert body — not a new task, just a new branch.

3. **Export CSV scope: streaming vs. in-memory**
   - What we know: UI-SPEC resolved export as CSV for the current filtered result set (all columns, no pagination limit, backend streams).
   - What's unclear: The expected maximum row count and whether `StreamingResponse` with a generator is needed, or if a simple synchronous CSV with a 10k-row cap is sufficient.
   - Recommendation: Implement as `StreamingResponse(csv_generator(), media_type="text/csv")` using Python's `csv.writer` + a generator. Cap at 50,000 rows with a header warning in the CSV if exceeded. This handles the typical analyst workflow without needing async streaming infrastructure.

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — all packages verified against npm registry, all versions confirmed in package.json
- Architecture: HIGH — grounded entirely in canonical project docs and verified codebase
- Pitfalls: HIGH — all pitfalls derived from specific code/schema details found in the codebase
- Test map: MEDIUM — test file names are proposed, not yet created; coverage estimates follow dev-spec §8 guidance

**Research date:** 2026-06-17
**Valid until:** 2026-07-17 (stable stack; key expiry risk is Next.js 16 or Recharts v3 API changes)
