# P10 — Signals / Ingest, and Sourcing

> Prereq reading: `00-CONTEXT.md` (track goal, target convention, binding coupling findings),
> `P1-MARKETPLACE.md` (folder convention + import-alias technique), `P8-NEWS-REPORTS.md` (which
> hands `ai_signal_service` here and warns that signals is not self-contained), `P5-DEALS.md`
> (which hands `models/counterparties.py` here), `P9-REQUESTS-PRICING.md` (which keeps
> `schemas/dashboard.py` in `app/schemas/` — `api/feed.py` depends on that decision).
> **P1–P9 must be merged and green before this phase starts.**

**Goal:** the signal/ingest pipeline moves into `backend/app/domains/signals/`, and **sourcing
splits out** into `backend/app/domains/sourcing/`. Full gate green. No behavior change.

## Scope decisions

### Sourcing is not part of this domain — split it out

`sourcing_service` imports `models/marketplace.SellerOffer`, `models/requests.Request`,
`models/sourcing.{InventoryItem,PartnerSupplier,SourcingRun}` and `schemas/sourcing.MarketIntelRow`.
It imports **nothing from signals or sources**. Its docstring describes a different feature
entirely: *"AI sourcing waterfall + market intelligence… inventory (1) → partner suppliers (2) →
marketplace offers (3) → import"* for a buyer request.

It is the AI-broker sourcing surface, not signal ingest. Four cohesive files, disjoint call sites,
its own folder, its own commit.

### Signals and sources stay together — one domain, deliberately

Unlike P7 and P9, this phase does **not** split further, and the reasoning is worth recording
because the file-level evidence looks like it points the other way:

- `signal_service` imports only `models/signals` + enums. `RawItem` is referenced **only under
  `if TYPE_CHECKING:`**.
- `raw_pipeline` has **zero runtime `from app.` imports**. `Source` is `TYPE_CHECKING`-only.
- `source_service` imports only `models/sources.Source`; `source_health_service` imports no app
  models at all.

So the two halves are barely coupled at import level and could be split. They are kept together
because **`ai_signal_service` genuinely spans both** — it writes `ParseRun` (sources) and `Signal`
(signals) in one orchestration — and because `raw_items → signals` is one pipeline that the whole
codebase reasons about as one thing. Splitting would put the pipeline's two ends in two folders
and leave its orchestrator arbitrarily in one of them. Low import coupling is not the same as low
conceptual coupling; here the roadmap's grouping is right.

### `models/counterparties.py` — moves here, and **is not dead code**

P5 handed this over noting its only repo-wide reference is the models barrel, and flagged it as
possibly dead ORM. **Resolved: it must stay, and the barrel import is load-bearing.**

`models/signals.py:100` declares:

```python
counterparty_id: Mapped[int | None] = mapped_column(
    Integer, ForeignKey("counterparties.id"), nullable=True
)
```

That is a **string-based FK target**. `Base.metadata` only knows the `counterparties` table
because the barrel imports the module. Delete it as "unused" and `signals.counterparty_id` points
at a table that no longer exists in metadata — alembic autogenerate and `create_all` both break.

The accurate statement is narrower than "dead": the `Counterparty` / `CounterpartyAlias` **ORM
classes** have no Python consumer (every access is raw SQL in `seed_showcase.py` or via the
`signals` FK), while the **module import** is required. It moves to
`app/domains/signals/counterparty_models.py` and keeps its barrel line. Whether the entity-
resolution background process the docstring describes ever shipped is a separate product question
— do not answer it with a deletion during a migration.

### `app/ingest/` stays put — and now imports across a domain boundary

`00-CONTEXT.md` leaves `app/ingest/` as-is (it has its own per-type adapter structure). But **9
files inside it import `app.models.sources`** — `base.py` plus the seven adapters
(`cbu_rates`, `html_table`, `llm_page`, `rss`, `telegram_channel`, `uzex`, `xarid`).

After this phase, a package deliberately excluded from the reorg imports
`app.domains.signals.source_models`. That is the largest single group of call sites in this phase
and the thing that makes it distinctive. It is **accepted, not a problem to solve**: `app/ingest/`
is an adapter layer over the source/raw-item model, so depending on it is its job. Do not add a
re-export shim in `app/ingest/` to hide the path — that is exactly the "why does this exist in two
places" confusion `00-CONTEXT.md` bans.

### `app/tasks/` stays put

`ingest.py`, `ingest_cbu.py`, `ingest_html_table.py`, `ingest_llm_page.py`, `ingest_rss.py`,
`parse.py`, `parse_telegram.py`, `nightly_catchup.py`, `rescore.py` all stay. Only their inner
import lines change. `_TASK_MODULES`, `task_routes` and the beat schedule are untouched.

## `api/feed.py` reads a view, not the ORM

Worth knowing before you move it: `app/api/feed.py` imports **no model at all**. Its `from app.`
lines are `api/deps`, `core/db`, `core/feed_bus`, `models/staff.StaffUser` and
`schemas/dashboard.{FeedItem,FeedPage}`. It reads `v_live_feed` — a **database view** — through
raw SQL, keyset-paginated.

Two consequences:

1. Moving it into `app/domains/signals/` gives that folder a file whose real contract is a DB
   view and `schemas/dashboard.py` (which stays in `app/schemas/` by P9's decision). Note this in
   the package docstring alongside the news pointer P8 asks for — the feed's coupling to
   `v_live_feed` is invisible to every import-based tool.
2. Nothing in this phase can break the feed via imports, and nothing in this phase can *fix* a
   view/column mismatch either. The view is defined in migrations, not in `app/`.

## Files moving

### 1. sourcing → `app/domains/sourcing/` (do this first — 4 files, fully disjoint)

| From | To |
|---|---|
| `app/models/sourcing.py` | `app/domains/sourcing/models.py` |
| `app/schemas/sourcing.py` | `app/domains/sourcing/schemas.py` |
| `app/services/sourcing_service.py` | `app/domains/sourcing/service.py` |
| `app/api/sourcing.py` | `app/domains/sourcing/api_admin.py` |

Call sites: `app/models/__init__.py` (barrel line 144), `tests/test_sourcing.py`, `app/main.py:85`.
That is all — `models.sourcing` has 4 referencing files, `schemas.sourcing` 3, `sourcing_service` 2.

### 2. signals → `app/domains/signals/`

| From | To |
|---|---|
| `app/models/signals.py` | `app/domains/signals/models.py` |
| `app/models/sources.py` | `app/domains/signals/source_models.py` |
| `app/models/counterparties.py` | `app/domains/signals/counterparty_models.py` |
| `app/services/signal_service.py` | `app/domains/signals/service.py` |
| `app/services/ai_signal_service.py` | `app/domains/signals/ai.py` |
| `app/services/raw_pipeline.py` | `app/domains/signals/raw_pipeline.py` |
| `app/services/source_service.py` | `app/domains/signals/sources.py` |
| `app/services/source_health_service.py` | `app/domains/signals/source_health.py` |
| `app/api/feed.py` | `app/domains/signals/api_feed.py` |
| `app/api/sources.py` | `app/domains/signals/api_sources.py` |
| `app/api/admin_sources.py` | `app/domains/signals/api_admin.py` |

## Call sites to update

Counts measured on the **pre-P1** tree. **Re-run the greps against the post-P9 tree before
starting.**

- **`app.models.sources`** (26 files) — the bulk of the phase:
  - Barrel: `app/models/__init__.py` line 143.
  - **`app/ingest/` (9 files):** `base.py`, `cbu_rates/adapter.py`, `html_table/adapter.py`,
    `llm_page/adapter.py`, `rss/adapter.py`, `telegram_channel/adapter.py`, `uzex/adapters.py`,
    `xarid/adapters.py`.
  - Services: `ai_signal_service`, `news_service` (→ `app/domains/news/service.py` after P8),
    `raw_pipeline`, `signal_service` (`TYPE_CHECKING` block), `source_service`.
  - API: `app/api/sources.py`. Tasks: `app/tasks/{ingest,ingest_cbu,parse,parse_telegram}.py`.
  - Tests: `test_{ai_signal_service,migration_0003,news_filter_sql_db,parse_raw_item,
    raw_pipeline_dedupe,rbac_dashboard,source_failure_alert}.py`.
- **`app.models.signals`** (10 files): barrel line 142, `ai_signal_service`, `alert_service`,
  `lead_score_recompute_service` (both P11 — they read signals across the boundary, expected),
  `news_service` (P8), `signal_service`, `app/tasks/parse_telegram.py`,
  `tests/test_{ai_signal_service,alert_service,news_filter_sql_db}.py`.
- **`app.models.counterparties`** (1 file): barrel line 39 only.
- **`signal_service`** (4), **`raw_pipeline`** (2), **`source_service`** (3),
  **`source_health_service`** (3), **`ai_signal_service`** (4) — all small, mostly
  namespace-style, so the alias fix covers them. `source_service` is imported by
  `app/api/admin_settings.py` (shared kernel, stays — import line only).
- **Routers:** `app.api.feed` → `app/main.py:58` + `tests/test_{feed_performance,feed_sse,
  needs_review_feed,rbac_dashboard,telegram_channel_close}.py`; `app.api.sources` →
  `app/main.py:84` **only**; `app.api.admin_sources` → `app/main.py:48` +
  `tests/test_{admin_settings_api,source_token_spend}.py`.
- **`TYPE_CHECKING` blocks:** `signal_service.py:37` and `raw_pipeline.py:40` import from
  `app.models.sources` inside `if TYPE_CHECKING:`. A path-level sed catches them correctly — just
  do not be surprised that these two files show up in the `models.sources` grep despite having no
  runtime dependency on it.

## Route checks — clean, including two more bare-`/admin` routers

Prefixes: `feed` → `/feed`, `sources` → `/sources`, `admin_sources` → `/admin`,
`sourcing` → `/admin`.

**Two routers on the bare `/admin` prefix again** (the third and fourth in this track, after
`admin_verification` in P2 and `admin_licenses` in P6). Checked — no collision:

| Router | First path segments |
|---|---|
| `admin_sources` | `/source-types`, `/sources/health`, `/sources/{source_id}/reprocess`, `/llm-spend`, `/source-groups`, `/sources/brief`, `/sources/{source_id}/group` |
| `sourcing` | `/inventory`, `/partners`, `/requests/{request_id}/source`, `/requests/{request_id}/sourcing`, `/intel/market` |

All distinct literal first segments; nothing shadows anything. Include order
(`admin_sources` at `main.py:191`, `sourcing` at `:226`) is irrelevant.

> Within `admin_sources`, `/sources/health` and `/sources/brief` are declared **before**
> `/sources/{source_id}/…`, so the literals win. Same intra-file ordering rule as
> `portal/manufacturers.py` in P7: **move the file byte-for-byte apart from its import block and
> do not reorder route declarations.**

## Steps

Two commits: **(a)** sourcing, **(b)** signals.

1. Re-run the grep inventory against the post-P9 tree.
2. **Commit (a) — sourcing:** create `app/domains/sourcing/__init__.py`, `git mv` the 4 files, fix
   internal imports, update the barrel line for `sourcing.py` (144), update
   `tests/test_sourcing.py` and `app/main.py:85`, update mypy config, full gate, commit.
3. **Commit (b) — signals:** create `app/domains/signals/__init__.py` **with a docstring** noting
   (i) that `api_feed.py`'s real contract is the `v_live_feed` DB view, not the ORM, and (ii) that
   news articles are `Signal` rows with `kind='news'` and an `ai.news` JSONB block, per P8.
4. `git mv` the 11 files. Do not reorder anything inside them.
5. Fix internal imports within the moved set (`ai.py` → `models`, `source_models`,
   and `app.domains.<reference>.{grade,relevance}` once P11 places those; `service.py` and
   `raw_pipeline.py` `TYPE_CHECKING` blocks → `source_models`; `sources.py` → `source_models`).
6. Update the `app/models/__init__.py` barrel lines for `signals.py` (142), `sources.py` (143)
   and `counterparties.py` (39), preserving FK-order position. **Keep the counterparties line** —
   see the scope note.
7. Replace call sites:
   - `app.models.signals` → `app.domains.signals.models`
   - `app.models.sources` → `app.domains.signals.source_models`
   - `app.models.counterparties` → `app.domains.signals.counterparty_models`
   - `app.models.sourcing` → `app.domains.sourcing.models`
   - `app.schemas.sourcing` → `app.domains.sourcing.schemas`
   - `app.services.signal_service` → `app.domains.signals.service`
   - `app.services.ai_signal_service` → `app.domains.signals.ai`
   - `app.services.raw_pipeline` → `app.domains.signals.raw_pipeline`
   - `app.services.source_service` → `app.domains.signals.sources`
   - `app.services.source_health_service` → `app.domains.signals.source_health`
   - `app.services.sourcing_service` → `app.domains.sourcing.service`
   - `app.api.feed` → `app.domains.signals.api_feed`
   - `app.api.sources` → `app.domains.signals.api_sources`
   - `app.api.admin_sources` → `app.domains.signals.api_admin`
   - `app.api.sourcing` → `app.domains.sourcing.api_admin`
8. Update `app/main.py` import lines 48, 58, 84, 85. Leave every `include_router` call where it is.
9. mypy: add `app/domains/signals/{service,ai,raw_pipeline,sources,source_health}.py` and
   `app/domains/sourcing/service.py` to the services check, `app/domains/sourcing/schemas.py` to
   the schemas check — local commands + `.github/workflows/ci.yml` lines 75/78.
10. Full gate before each commit:
    - `cd backend && ruff check .`
    - `cd backend && mypy app/services app/domains/*/service.py app/domains/signals/{ai,raw_pipeline,sources,source_health}.py app/domains/requests/{analysis,rfq_push,supplier_matching}.py app/domains/pricing/analysis.py app/domains/news/{dedup,reports}.py app/domains/lab_orders/samples.py app/domains/compliance/{substances,substance_ai,licenses}.py app/domains/deals/{escrow,rfq}.py app/domains/contracts/{render,eimzo}.py app/domains/companies/directory.py app/domains/verification/{checks,registry}.py app/domains/marketplace/{requests,compliance}.py --ignore-missing-imports`
    - `cd backend && mypy app/schemas app/domains/*/schemas.py app/domains/requests/{webapp_schemas,analysis_schemas}.py app/domains/compliance/{substance_schemas,substance_match_schemas}.py app/domains/contracts/eimzo_schemas.py --ignore-missing-imports`
    - `cd backend && pytest tests/ -q` (full suite, not a subset)

## Verification

- `ruff check .` — no new lint errors.
- Both `mypy` invocations — clean.
- `pytest tests/ -q` — full suite green. Highest-signal files: `test_raw_pipeline_dedupe.py`,
  `test_parse_raw_item.py`, `test_parse_xarid_item.py`, `test_uzex_accuracy.py`,
  `test_ai_signal_service.py`, `test_signal*`, `test_source_health.py`,
  `test_source_failure_alert.py`, `test_source_token_spend.py`, `test_feed_performance.py`,
  `test_feed_sse.py`, `test_needs_review_feed.py`, `test_rbac_dashboard.py`,
  `test_telegram_channel_close.py`, `test_migration_0003.py`, `test_sourcing.py`.
- **Adapter-registry check — specific to this phase.** Adapters self-register at import time into
  `app/ingest/registry.py`, and `00-CONTEXT.md`'s own gotcha is that registration only happens in
  the process that imports the module — which is why they are imported in **both** `app/main.py`
  and `app/tasks/ingest.py`. All 9 ingest files change imports here. After the move, assert the
  registry contains every expected `type_name` **in both processes**: construct the app and check
  `GET /admin/source-types`, and separately import `app.tasks.ingest` in a fresh interpreter and
  check the registry. A missed import here breaks ingest at dispatch, not at boot.
- **`Base.metadata` parity:** `sorted(Base.metadata.tables)` before and after — identical.
  `counterparties` **must** still be present; its absence is the specific failure the scope note
  above predicts.
- **Route-parity check:** compare `sorted((r.path, tuple(sorted(r.methods))) for r in app.routes)`
  before and after — byte-identical, after each commit. Plus the intra-file order check on
  `admin_sources`: confirm `GET /api/v1/admin/sources/health` resolves to the health handler and
  not to `/sources/{source_id}` with `source_id="health"`.
- **SSE check:** `api_feed.py` serves the live feed over SSE via `core/feed_bus`. `test_feed_sse.py`
  covers it; confirm it still streams after the move rather than assuming a green suite proves the
  subscription wiring survived.
- `uv run uvicorn app.main:app --reload` boots without import errors.
- `grep -rn "app\.models\.\(signals\|sources\|sourcing\|counterparties\)\b\|app\.schemas\.sourcing\b\|app\.services\.\(signal_service\|ai_signal_service\|raw_pipeline\|source_service\|source_health_service\|sourcing_service\)\b\|app\.api\.\(feed\|sources\|admin_sources\|sourcing\)\b" backend/app backend/tests` returns nothing.
