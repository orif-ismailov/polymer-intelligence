# P8 — News / Reports domain migration

> Prereq reading: `00-CONTEXT.md` (track goal, target convention, binding coupling findings),
> `P1-MARKETPLACE.md` (folder convention + import-alias technique). **P1–P7 must be merged and
> green before this phase starts.**

**Goal:** `news_service`, `news_dedup`, `report_service`, `models/reports.py`,
`schemas/reports.py`, `api/reports.py`, `api/portal/news.py` and `api/webapp/news.py` move into
`backend/app/domains/news/`. Full gate green. No behavior change.

## Size

**~20 unique files.** Small, and the routers are unusually clean — `/admin/reports`,
`/portal/news`, `/webapp/news` are three distinct, uncontested prefixes with no cross-router
ordering dependency and nothing to relocate.

## Scope decisions — half the roadmap's list belongs elsewhere

`00-CONTEXT.md` assigns six services to this phase. **Three of them have nothing to do with
news.** Checked by consumer, not by name:

- **`ai_signal_service` → P10 (Signals/Ingest).** Its docstring: *"helpers for the
  `parse_telegram_item` orchestrator"*. It imports `models/signals.py`, `models/sources.py`
  (`ParseRun`, `RawItem`) and `parsing.schemas`, and its only consumers are `app/tasks/parse.py`
  and `app/tasks/parse_telegram.py`. Zero news files touch it. It is the signal parse pipeline.
- **`grade_service` → the reference/products domain (P11).** Pure UZEX polymer-grade extraction:
  a `product_grades` lookup by code, then a regex fallback. It has **no `from app.` imports at
  all** — it takes a session and runs bound-parameter `text()` SQL. Consumers are
  `ai_signal_service` and the two parse tasks. No news.
- **`relevance_service` → the reference/products domain (P11).** Maps raw product text to a
  `product_id` through the synonym dictionary. Also **no `from app.` imports** — bound-parameter
  `text()` SQL only. Its consumers span four domains: `ai_signal_service` (signals),
  `news_service` (news), `offer_service` (marketplace), the two parse tasks, and
  `seed_reference.py`.

  > `relevance_service` and `grade_service` belong together and belong to neither news nor
  > signals. Both are stateless reference-dictionary lookups over `products` / `product_grades`,
  > which is exactly what `product_service` (already in P11's leftovers list) owns. Grouping the
  > three into a `reference`/`products` domain keeps them available to signals, news **and**
  > marketplace without any one of those claiming them. Decide it in P11; this plan only asserts
  > they are not P8's.

- **`parsing/` stays put — it is not in `app/`.** `parsing/news_extractor.py` and
  `parsing/news_schemas.py` live in `backend/parsing/`, a **top-level package** beside `app/`,
  not inside it. This track reorganizes `backend/app/`. `parsing/` also has its own mypy
  carve-out (`module = ["parsing.*"]` in `pyproject.toml`, with a comment explaining why the
  services gate must not leak into it) and its own versioned-prompt discipline. Nothing here
  moves it, and `news_service`'s `from parsing.news_extractor import …` is unchanged.
- **`app/tasks/{parse,reports,nightly_catchup}.py` stay put.** `app/tasks/` is not moved by this
  track. The `notify`-queue publishers (`publish_report_to_channel`, `publish_breaking_news`) and
  the two beat report generators keep their names, routes and `_TASK_MODULES` entries; only their
  inner import lines change.

## Read this before you start: **this domain owns no article model**

There is no `news_articles` table and no `models/news.py`. A news article **is a `Signal` row**
with `kind='news'`, and the entire rich classification — headline, category, importance,
market_impact, summary — lives in the `signals.ai` JSONB block under `ai.news`.
`news_service`'s docstring records the decision: *"storing the rich classification under
signals.ai JSONB (Option A — no schema migration)."*

Consequences that matter for this phase:

1. `app/domains/news/` will contain `models.py` holding **only `Report`**. Someone opening the
   folder looking for "the news model" will not find one. Say so in the package docstring of
   `app/domains/news/__init__.py` — one sentence pointing at `models/signals.py` and `ai.news`.
   That sentence is the single highest-value artifact of this phase for future navigability, and
   it is exactly the kind of thing a mechanical file move loses.
2. `news_service` imports `app.models.signals.Signal` and will keep doing so across a domain
   boundary once P10 lands. That is correct and expected — do not try to give news its own model.
3. **A note for P10:** signals is not self-contained. News and reports read `Signal` and write
   `signals.ai`, so P10's call-site inventory must include this domain, and any future thought
   of narrowing `Signal` needs to account for the `ai.news` block.

## Files moving

| From | To |
|---|---|
| `app/models/reports.py` | `app/domains/news/models.py` |
| `app/schemas/reports.py` | `app/domains/news/schemas.py` |
| `app/services/news_service.py` | `app/domains/news/service.py` |
| `app/services/news_dedup.py` | `app/domains/news/dedup.py` |
| `app/services/report_service.py` | `app/domains/news/reports.py` |
| `app/api/reports.py` | `app/domains/news/api_admin.py` |
| `app/api/portal/news.py` | `app/domains/news/api_portal.py` |
| `app/api/webapp/news.py` | `app/domains/news/api_webapp.py` |

## Call sites to update

Counts measured on the **pre-P1** tree. **Re-run the greps against the post-P7 tree before
starting.**

- **`app.models.reports`** (3 files): `app/models/__init__.py` (barrel, line 139 — update in
  place, keep FK-order position), `app/api/reports.py`, `app/services/report_service.py`. The
  `__all__` entry (`Report`) is name-only — no edit.
- **`app.schemas.reports`** (4 files): `app/api/reports.py`, `app/api/portal/news.py`,
  `app/api/webapp/news.py`, `app/api/public.py`.
- **`news_service`** (10 files): `app/api/admin_settings.py`, `app/api/portal/news.py`,
  `app/api/webapp/news.py`, `app/api/public.py`, `app/services/report_service.py`,
  `app/tasks/parse.py`, plus `tests/test_{news_articles_api,news_filter_sql_db,parse_news_item,
  public_api}.py`.
- **`news_dedup`** (3 files): `app/services/news_service.py`, `app/services/report_service.py`,
  `tests/test_news_dedup.py`. Both importers move with it — these are internal imports, fixed in
  step 4, not call sites.
- **`report_service`** (11 files): `app/api/admin_settings.py`, `app/api/portal/news.py`,
  `app/api/reports.py`, `app/api/webapp/news.py`, `app/tasks/reports.py`, plus
  `tests/test_{daily_digest,news_articles_api,news_filter_sql_db,report_top_news,reports,
  telegram_digest}.py`.
- **Routers:** `app.api.reports` → `app/main.py:83` + `tests/test_reports.py`;
  `app.api.portal.news` → `app/main.py:74` + `tests/test_{portal_news_api,public_api}.py`;
  `app.api.webapp.news` → `app/main.py:91` + `tests/test_{portal_news_api,reports}.py`.
- **`app/api/admin_settings.py`** imports both `news_service` and `report_service`. It is the
  runtime-settings surface (`news_ai_enabled`, `news_require_approval`, `report_auto_publish`,
  `news_prompt_version`, `news_refresh_interval_minutes`) and is **shared kernel — it stays in
  `app/api/`**. Only its import lines change.
- **`app/services/settings_service.py`** imports `parsing.news_*` to validate the
  `news_prompt_version` setting. It is shared kernel, stays, and its `parsing.` import is
  untouched — listed here only so it is not mistaken for a missed call site.

### One function-local import to expect

`report_service` imports `news_service` **inside a function**, not at module level (its
module-level `from app.` block covers only config, languages, time, enums, `models/reports` and
`news_dedup`). Both files land in the same folder, so this becomes an intra-domain import — but
grep for it explicitly rather than trusting the module-level import block, or you will miss it.

## No misplaced routes — checked

All three routers own distinct, uncontested prefixes (`/admin/reports`, `/portal/news`,
`/webapp/news`). No other router declares anything under them, none of them declares anything
outside them, and `main.py` carries no ordering comment touching any of the three. Nothing to
relocate; route-parity is a formality here rather than the primary gate it was in P6.

## Steps

1. Re-run the grep inventory against the post-P7 tree.
2. Create `app/domains/news/__init__.py` — **with the docstring described above** (no news model;
   articles are `Signal` rows with `kind='news'` and an `ai.news` JSONB block).
3. `git mv` the 8 files to their new paths (preserves history).
4. Fix internal imports within the moved set: `service.py` → `dedup`, `reports.py` → `dedup`,
   `reports.py` → `service` (the function-local one), `api_*.py` → `service` / `reports` /
   `schemas` / `models`.
5. Update the `app/models/__init__.py` barrel line for `reports.py` (139), preserving FK-order
   position.
6. Replace call sites:
   - `app.models.reports` → `app.domains.news.models`
   - `app.schemas.reports` → `app.domains.news.schemas`
   - `app.services.news_service` → `app.domains.news.service`
   - `app.services.news_dedup` → `app.domains.news.dedup`
   - `app.services.report_service` → `app.domains.news.reports`
   - `app.api.reports` → `app.domains.news.api_admin`
   - `app.api.portal.news` → `app.domains.news.api_portal`
   - `app.api.webapp.news` → `app.domains.news.api_webapp`
   Split any mixed `from app.services import (…)` block by hand and alias — `app/tasks/parse.py`
   and `app/api/admin_settings.py` both import moving names next to shared-kernel ones.
7. Update `app/main.py` import lines 74, 83, 91. Leave every `include_router` call where it is.
8. Update `backend/pyproject.toml` mypy overrides (the `app.domains.*` blocks from P2 — verify
   present) and the mypy invocations, local + `.github/workflows/ci.yml` lines 75/78, adding
   `app/domains/news/{service,dedup,reports}.py` to the services check and
   `app/domains/news/schemas.py` to the schemas check.
9. Run the full gate and fix anything red:
   - `cd backend && ruff check .`
   - `cd backend && mypy app/services app/domains/*/service.py app/domains/news/{dedup,reports}.py app/domains/lab_orders/samples.py app/domains/compliance/{substances,substance_ai,licenses}.py app/domains/deals/{escrow,rfq}.py app/domains/contracts/{render,eimzo}.py app/domains/companies/directory.py app/domains/verification/{checks,registry}.py app/domains/marketplace/{requests,compliance}.py --ignore-missing-imports`
   - `cd backend && mypy app/schemas app/domains/*/schemas.py app/domains/compliance/{substance_schemas,substance_match_schemas}.py app/domains/contracts/eimzo_schemas.py --ignore-missing-imports`
   - `cd backend && pytest tests/ -q` (full suite, not a subset)
10. Commit once everything is green.

## Verification

- `ruff check .` — no new lint errors.
- Both `mypy` invocations — clean.
- `pytest tests/ -q` — full suite green. Highest-signal files: `test_reports.py`,
  `test_daily_digest.py`, `test_telegram_digest.py`, `test_report_top_news.py`,
  `test_news_articles_api.py`, `test_news_dedup.py`, `test_news_filter_sql_db.py`,
  `test_parse_news_item.py`, `test_portal_news_api.py`, `test_public_api.py`.
- **Prompt-version pins must not move.** `report_service` renders against `report_v*`
  (`REPORT_PROMPT_VERSION`, currently v6) and the news classifier is selected at **runtime**
  via the `news_prompt_version` app-setting. Prompts are versioned and immutable by repo rule.
  Confirm this phase changes neither the pinned version nor the setting's default — a move must
  not touch prompt selection.
- **Report lifecycle is human-in-the-loop.** `draft → pending_approval → approved → published`,
  with `report_auto_publish` off by default. After the move, confirm a generated report still
  lands as `draft` and does **not** auto-publish — an accidental default flip would post to
  `NEWS_CHANNEL_ID` unreviewed. `test_reports.py` and `test_daily_digest.py` cover this; read
  their assertions rather than assuming a green suite proves it.
- **Route-parity check:** compare `sorted((r.path, tuple(sorted(r.methods))) for r in app.routes)`
  before and after — byte-identical.
- `uv run uvicorn app.main:app --reload` boots without import errors.
- `grep -rn "app\.models\.reports\|app\.schemas\.reports\|app\.services\.news_service\|app\.services\.news_dedup\|app\.services\.report_service\|app\.api\.reports\|app\.api\.portal\.news\|app\.api\.webapp\.news" backend/app backend/tests` returns nothing.
