# P11 — The remainder: accounts, reference, alerts, notifications, storefront, and the kernel line

> Prereq reading: `00-CONTEXT.md`, and every prior `P<N>-*.md` — this phase is defined by what
> they left behind. **P1–P10 must be merged and green before this phase starts.**

**Goal:** place every remaining file in `app/models/`, `app/schemas/`, `app/services/` and
`app/api/` — either into a domain folder or into an **explicitly declared shared kernel** — so
that after this phase nothing is unplaced by accident. Full gate green. No behavior change.

## How this list was produced

Not from the roadmap. Every module under the four technical-layer folders was enumerated and the
claims of P1–P10 subtracted. What survived: **10 models, 8 schemas, 14 services, 20 routers.**
Re-run that subtraction before starting — it is the only reliable inventory for this phase:

```
# for each of app/models, app/schemas, app/services, app/api — list what still exists
# after P1-P10 and confirm it appears somewhere below.
```

## Finding 1 — P1 under-claimed five marketplace routers. **RESOLVED: P1 amended.**

`P1-MARKETPLACE.md` moves `app/api/portal/offers.py` and `app/api/offer_requests.py`. It leaves
**five more routers whose subject is unambiguously marketplace**:

| Router | Marketplace imports |
|---|---|
| `app/api/moderation.py` | `SellerOffer`, `schemas.marketplace`, `offer_service`, `offer_compliance_service` |
| `app/api/portal/market.py` | `SellerOffer`, `schemas.portal_market` |
| `app/api/portal/inquiries.py` | `OfferRequest`, `SellerOffer`, `schemas.marketplace`, `schemas.portal_market` |
| `app/api/webapp/market.py` | `SellerOfferFile`, `schemas.marketplace` |
| `app/api/webapp/seller.py` | `Seller`, `SellerOffer`, `SellerOfferFile`, `schemas.marketplace` |

Plus `app/schemas/portal_market.py`, imported only by `portal/market.py` and `portal/inquiries.py`.

P1 lists several of these as *call sites* — files whose imports get rewritten — rather than as
files that move. The result is that after the pilot phase, `app/api/` still holds five marketplace
surfaces, which directly undercuts the track's stated goal: finding "everything about offers"
would still mean visiting two directories.

**This has been applied.** `P1-MARKETPLACE.md` now moves all seven marketplace routers plus
`schemas/portal_market.py` — 13 files instead of 7 — and carries the two gotchas the extra files
bring with them: `portal/market.py`'s load-bearing intra-file route order (`/{offer_id}` declared
last on purpose), and the fact that `portal/market.py` and `portal/inquiries.py` import P2's
shared portal helpers, which P1 must leave alone because it runs first.

**So there is nothing to sweep here** — unless P1 somehow shipped from an older copy of its plan.
Confirm before starting:
`grep -rln "SellerOffer\|schemas\.marketplace" backend/app/api` should return nothing. If it
returns those five routers, sweep them into `app/domains/marketplace/` as this phase's first
commit; a late move beats a permanent residue.

> Worth generalizing: P1 was written before the router-inventory habit that P2–P10 adopted.
> Before starting this phase, spot-check each earlier domain folder for the same shape — a
> router in `app/api/` importing that domain's models and nothing else.

## Finding 2 — four services routed here actually belong to earlier phases

Checked by model ownership, the same test that reassigned services in P5, P7, P8 and P10:

- **`lead_score_recompute_service` → P10 (signals).** It imports `models/signals.Signal` and
  recomputes lead scores on prompt-version change. It is a signals service; it appears in P11's
  leftovers only because `00-CONTEXT.md`'s roadmap listed it there. If P10 has shipped, move it
  here into `app/domains/signals/`; otherwise amend P10.
- **`fx_service` → P9 (pricing).** No `from app.models` imports at all — bound-parameter SQL over
  `fx_rates`, upsert plus convert-on-read. Its only non-test consumer is `app/tasks/ingest_cbu.py`.
  It is a currency concern next to `price_points`. Alternative home is P10 (its consumer is an
  ingest task); pricing is the better fit because the thing it exists for is money, not fetching.
- **`userbot_health_service` → P10 (signals).** No `from app.models` imports; it reads the
  userbot's Redis heartbeat and raises a deduped `source_failure` admin alert when it goes stale
  past `USERBOT_SILENCE_SECONDS`. That is the same job `source_health_service` does for sources,
  and P10 already owns that one — they belong side by side. Its only non-test consumer is
  `app/tasks/userbot_health.py`, which stays in `app/tasks/`.
- **`review_service` + `models/reviews.py` + `models/media.py` — this phase owns them.**
  P3 argued for pulling them in early; the decision was to leave them here, and `P3-COMPANIES.md`
  records that as settled. They are **not** conditional and not a reassignment — they are P11 work,
  and they are the reason the companies domain is incomplete between P3 and this phase.
  See "Finding 4" below for the move itself.

## Finding 3 — client identity joins requests, resolving P9's squatters

`client_service` verifies Telegram Web App initData and upserts `Client` — and `Client` is
declared in `models/requests.py`, which P9 already moved to `app/domains/requests/models.py`.

So there is no separate "clients" domain to build. `client_service`, `app/api/webapp/auth.py` and
`app/api/webapp/me.py` join the requests domain:

| From | To |
|---|---|
| `app/services/client_service.py` | `app/domains/requests/clients.py` |
| `app/api/webapp/auth.py` | `app/domains/requests/api_webapp_auth.py` |
| `app/api/webapp/me.py` | `app/domains/requests/api_webapp_me.py` |

This also **resolves P9's open item**: the `ClientProfileOut` / `ClientProfilePatch` classes P9
left in `app/domains/requests/webapp_schemas.py` as "client-domain squatters" are not squatters
after all — their consumer now lives in the same folder. Delete that caveat from P9 when this
lands; no extraction is needed.

## Finding 4 — completing the companies domain (decided: deferred from P3)

`CompanyReview` and `CompanyMedia` are company-owned — one review row per *(subject company,
author company)* pair, and images a *company's* public profile references. P3 leaves them in
`app/models/` by decision, so from P3 until this phase "everything about companies" is not yet one
folder. This is where that is closed:

| From | To |
|---|---|
| `app/models/reviews.py` | `app/domains/companies/review_models.py` |
| `app/models/media.py` | `app/domains/companies/media_models.py` |
| `app/services/review_service.py` | `app/domains/companies/reviews.py` |

Call sites are few: `review_service` is imported only by `app/api/public.py` (→
`app/domains/storefront/api.py` in this phase — sequence this move **after** storefront, or update
the import twice) and by `app/domains/companies/api_portal.py`. `models/media.py` is additionally
read by `app/seed/seed_showcase_media.py`, which stays in `app/seed/`. Barrel lines: `media.py`
127, `reviews.py` 141 — preserve FK-order position.

Two things P3 deliberately left in a temporary state that this phase now tidies:
`_summary_out`/`_detail_out` reaching back into `app/models/reviews.py`, and
`api_portal.py` importing `review_service` from `app.services`. Both become intra-domain imports.
**That is the whole cleanup** — do not take it as licence to restructure the review routes.

## The domains this phase creates

### 1. `app/domains/accounts/` — portal identity

| From | To |
|---|---|
| `app/models/accounts.py` | `app/domains/accounts/models.py` |
| `app/schemas/portal.py` | `app/domains/accounts/schemas.py` |
| `app/services/otp_service.py` | `app/domains/accounts/otp.py` |
| `app/api/portal/auth.py` | `app/domains/accounts/api_portal.py` |

`otp_service` was excluded from P2 on the grounds that phone-OTP login is account authentication,
not company verification. This is where it lands. `models/accounts.py` (`UserAccount`,
`SmsSendLog`) has **48 importing files** — nearly every portal router, mostly via
`deps.get_current_account`.

> **High fan-in does not make it shared kernel.** `models/companies.py` has 76 importers and is
> unambiguously a domain. The test applied throughout this track is *does it have an owner* —
> accounts does (`otp_service` creates and authenticates them). Contrast `models/staff.py` below.

### 2. `app/domains/reference/` — products, grades, synonyms

| From | To |
|---|---|
| `app/models/reference.py` | `app/domains/reference/models.py` |
| `app/schemas/reference.py` | `app/domains/reference/schemas.py` |
| `app/services/product_service.py` | `app/domains/reference/service.py` |
| `app/services/relevance_service.py` | `app/domains/reference/relevance.py` |
| `app/services/grade_service.py` | `app/domains/reference/grades.py` |
| `app/api/admin_products.py` | `app/domains/reference/api_admin.py` |
| `app/api/portal/reference.py` | `app/domains/reference/api_portal.py` |
| `app/api/webapp/reference.py` | `app/domains/reference/api_webapp.py` |

This is the home P8 and P10 promised for `relevance_service` and `grade_service`. All three
services are reference-dictionary lookups over `products` / `product_grades`; `product_service`
imports `models/reference.Product`, and the other two reach the same tables through
bound-parameter `text()` SQL with **no `from app.` imports at all**.

Consumers span four domains (signals, news, marketplace, requests), which is exactly why this is
its own domain rather than being claimed by any one of them.

### 3. `app/domains/alerts/`

| From | To |
|---|---|
| `app/models/alerts.py` | `app/domains/alerts/models.py` |
| `app/services/alert_service.py` | `app/domains/alerts/service.py` |
| `app/api/alert_rules.py` | `app/domains/alerts/api_admin.py` |

`alert_service` imports `models/alerts.{Alert,AlertRule,Delivery}` and nothing else domain-shaped.
`app/api/alert_rules.py` exports **two** routers (`router` and `alerts_router`) — `app/main.py`
imports both at lines 52–53. Move both; keep both `include_router` calls.

> `alert_service` has a **named mypy carve-out** in `pyproject.toml`
> (`module = ["app.services.alert_service"]`, relaxing `disallow_any_explicit` for the JSONB
> predicate interpreter, with a long comment justifying it). That override key **must be renamed**
> to `app.domains.alerts.service` or the carve-out silently stops applying and the services gate
> fails. This is the only per-module override in the file keyed to a moving service — do not miss
> it.

### 4. `app/domains/notifications/`

| From | To |
|---|---|
| `app/models/notifications.py` | `app/domains/notifications/models.py` |
| `app/schemas/portal_notification.py` | `app/domains/notifications/schemas.py` |
| `app/api/portal/notifications.py` | `app/domains/notifications/api_portal.py` |

**`notification_service` does not move** — it is shared kernel by `00-CONTEXT.md`'s explicit list,
imported by nearly every domain. So this domain owns the `PortalNotification` model and the portal
read surface, while the dispatcher stays in `app/services/`. That is a deliberate split; note it in
the package docstring so the next reader does not "reunite" them.

### 5. `app/domains/storefront/` — the anonymous public surface

| From | To |
|---|---|
| `app/schemas/public.py` | `app/domains/storefront/schemas.py` |
| `app/services/public_market_service.py` | `app/domains/storefront/service.py` |
| `app/api/public.py` | `app/domains/storefront/api.py` |

`public_market_service` reads `companies`, `marketplace`, `prices` and `reference` — four domains —
which looks like a reason to call it shared. It is not: its docstring is unusually clear that it is
a *surface*, not a utility — *"Everything here answers a question the logged-out home page asks and
nothing else does: the hero stat strip, the category tiles with their counts, the price…"*. One
consumer (`api/public.py`), one audience (anonymous visitors), one reason to change. That is a
bounded context whose data happens to be borrowed.

Named `storefront` rather than `public` so the folder does not read as a visibility modifier.

## The shared kernel — declared explicitly, and final

`00-CONTEXT.md` names a partial kernel. This phase **closes the list**, so that "still in
`app/services/`" stops being ambiguous between *kernel* and *not yet moved*. Record this list in
`app/services/__init__.py` and `app/api/__init__.py` docstrings — that is the artifact that makes
the reorg legible afterwards.

**Auth / authorization substrate** — stays:
`app/services/auth_service.py`, `app/models/staff.py`, `app/schemas/auth.py`, `app/api/auth.py`,
`app/api/admin_users.py`, `app/api/deps.py`, `app/api/portal/deps.py` (P2), `app/core/security.py`.

> Why staff is kernel while accounts is a domain: `models/staff.py` holds `StaffUser` **and**
> `AuditLog`. `AuditLog` is written by `audit_service` from nearly every domain, and `StaffUser` is
> a dependency of every admin router through `deps.require_admin`. Its 42 importers are not
> *users of a staff domain* — they are users of authorization and audit. It has no owner; it is
> substrate.

**Infrastructure** — stays: `audit_service`, `event_service`, `event_types`, `notification_service`,
`storage_service`, `settings_service`, `rate_limit`, `models/{events,integration,app_settings}.py`,
`schemas/admin_settings.py`, `api/admin_settings.py`, `api/health.py`, `api/telegram_webhook.py`.

**Dashboard presentation** — stays, per P9's decision: `schemas/dashboard.py`,
`dashboard_summary_service`, `app/api/dashboard.py`. A presentation layer for one UI spanning
seven domains. P9 argued the case; this phase does not reopen it. Keep the three together and say
in `schemas/dashboard.py`'s docstring that they are a set.

**Not in `app/`, untouched throughout:** `parsing/`, `app/ingest/`, `app/integrations/`,
`app/tasks/`, `app/seed/`, `app/core/`.

## Route checks

`admin_products` (`/admin/products`, `/admin/products/{product_id}`) and `admin_users`
(`/admin/users`) are the **fifth and sixth** routers on the bare `/admin` prefix, after
`admin_verification` (P2), `admin_licenses` (P6), `admin_sources` and `sourcing` (P10). Checked
against all four: every first segment is a distinct literal, nothing shadows anything, include
order is irrelevant.

`alert_rules` (`/alert-rules`), `portal/auth` (`/portal`), `portal/reference`
(`/portal/reference`), `webapp/reference` (`/webapp/reference`), `webapp/auth` (`/webapp/auth`),
`auth` (`/auth`) — all uncontested.

`webapp/me` sits on the bare `/webapp` prefix with `/me` only; P9 established it shares that prefix
with `webapp/requests` and `webapp/files` without collision, and after this phase all three are in
`app/domains/requests/`.

## Steps

Seven commits, each independently gate-green. Order is smallest-blast-radius first:

1. **Marketplace router sweep** — only if P1 shipped without the amendment (Finding 1).
2. **Reassignments** — `lead_score_recompute_service` and `userbot_health_service` → signals,
   `fx_service` → pricing, `review_service` + `models/{reviews,media}.py` → companies; only for
   whichever of P3/P9/P10 did not already absorb them (Finding 2).
3. **`notifications`** (3 files) — smallest new domain.
4. **`alerts`** (3 files) — **with the `pyproject.toml` override rename.**
5. **`storefront`** (3 files).
6. **`accounts`** (4 files) + **`reference`** (8 files) + **client-into-requests** (3 files).
7. **`companies` completion** (3 files — Finding 4). Last, because `review_service`'s other
   consumer is `app/api/public.py`, which becomes `app/domains/storefront/api.py` in step 5 —
   doing this after storefront means that import is rewritten once instead of twice.

For each: create `__init__.py` (with the docstrings called out above), `git mv`, fix internal
imports, update the `app/models/__init__.py` barrel line preserving FK order, replace call sites,
update `app/main.py` import lines, update `pyproject.toml` mypy overrides and the two mypy
invocations (local + `.github/workflows/ci.yml` lines 75/78), then run the full gate:

```
cd backend && ruff check .
cd backend && mypy app/services app/domains/*/service.py app/domains/*/*.py --ignore-missing-imports
cd backend && mypy app/schemas app/domains/*/schemas.py --ignore-missing-imports
cd backend && pytest tests/ -q
```

> By this phase the explicit per-file mypy lists accumulated since P1 are long and error-prone.
> **Consider collapsing them to `app/domains/` as a directory argument** once every domain exists —
> a single path that cannot go stale, matching how `app/services` and `app/schemas` are passed
> today. Do it as its own commit at the end, after confirming the file count checked does not drop.

## Verification

- `ruff check .` — no new lint errors.
- Both `mypy` invocations — clean. **Specifically confirm `alert_service`'s carve-out still
  applies** after the rename: a silently-dropped override shows up as new
  `disallow_any_explicit` errors, not as a config error.
- `pytest tests/ -q` — full suite green after each commit.
- **Route-parity check** after each commit: `sorted((r.path, tuple(sorted(r.methods))) for r in
  app.routes)` byte-identical. `alert_rules` exports two routers — parity catches a forgotten one.
- **`Base.metadata` parity:** `sorted(Base.metadata.tables)` identical after each commit.
- **Final sweep — the point of the whole phase.** After the last commit, these must all be true:
  - `ls app/models/` contains only `__init__.py`, `enums.py`, `staff.py`, `events.py`,
    `integration.py`, `app_settings.py` — **no `reviews.py`, no `media.py`** (Finding 4).
  - `ls app/schemas/` contains only `__init__.py`, `auth.py`, `dashboard.py`, `admin_settings.py`.
  - `ls app/services/` contains only the declared kernel: `audit_service`, `auth_service`,
    `event_service`, `event_types`, `notification_service`, `storage_service`, `settings_service`,
    `rate_limit`, `dashboard_summary_service`.
  - `ls app/api/` contains only `__init__.py`, `deps.py`, `auth.py`, `admin_users.py`,
    `admin_settings.py`, `dashboard.py`, `health.py`, `telegram_webhook.py`, `portal/deps.py`.
  - `app/api/portal/` and `app/api/webapp/` contain **only** `__init__.py` and `deps.py`.

  Anything else still present is either a missed file or a kernel decision nobody wrote down —
  both worth resolving before calling the track done.
- `uv run uvicorn app.main:app --reload` boots without import errors.
