# Backend domain reorg — context

**Track:** reorganize `backend/app/` from technical layers (`app/models/`, `app/services/`,
`app/schemas/`, `app/api/`) into bounded-context domain folders (`app/domains/<name>/`), one
domain at a time, tests green after every domain.

## Why

The backend has ~15 business domains (marketplace, verification, contracts, deals, escrow, lab,
news, ...) flattened across four top-level technical-layer folders (34 model files, 47 service
files, 24 schema files, ~60 router files). Finding "everything about contracts" means jumping
across four directories, each with a dozen-plus unrelated siblings — this was raised as a growing
navigability problem as the codebase has grown past the original signal-pipeline scope into
marketplace, verification/portal, contracts, deals, escrow, labs, and news tracks.

CQRS was considered and rejected: it separates read/write, not domains — irrelevant to
navigability and would add indirection on top of the existing problem. Full tactical DDD
(repository pattern abstracting SQLAlchemy, domain entities split from ORM models, event
sourcing) was also rejected: the service layer already functions as a reasonable application
layer over sufficiently rich ORM models (state machines, actor-rule tables per domain already
document real invariants), and there's no persistence-swap or test-isolation need to justify a
repository abstraction. What's adopted is DDD's **strategic** pattern only — group each bounded
context's models/schemas/service/api together — nothing tactical.

## Findings from the coupling research (binding for every phase)

- ~1800 `app.services.X` / `app.models.X` / `app.schemas.X` / `app.api.X` import references
  repo-wide (`app/` + `tests/`), all literal strings — mechanical (grep+sed), not a logic
  rewrite, but real volume per domain.
- **"Repo-wide" means the repo root, not `backend/`.** `telegram/` and `userbot/` are
  repo-root packages that import backend modules, and they are mounted read-only into the
  containers rather than vendored — so nothing about `backend/`'s own import graph reveals
  them. Every sweep, grep and inventory in this track must cover
  `backend/app backend/tests telegram userbot`. *Added after P1 scoped its inventory to
  `app/` + `tests/` and missed five call sites in `telegram/handlers/moderation.py`; the
  worker and bot would have broken at runtime, and it surfaced only as seven test failures.
  P2 and P3 each hit the same files again (`telegram/handlers/verification.py`).* Known
  reach as of P3: `telegram/` imports `app.services.client_service` (P11) and
  `app.core.languages`; `userbot/` imports `app.services.raw_pipeline`, `app.models.sources`
  and `app.ingest.base` (P10).
- `app/models/__init__.py` is a genuine barrel (imports every model in FK order, feeds
  `Base.metadata` for alembic). Moving a model file just means updating its barrel line in
  place — SQLAlchemy resolves FKs from `Base.metadata` after all models load, not from Python
  import order, and ruff's isort sorts the block anyway, so relative order is not something
  to preserve.
- **The barrel must import relocated models as MODULES, never by name.** Use
  `import app.domains.<name>.models  # noqa: F401`, not
  `from app.domains.<name>.models import Company`. A domain model module opens with
  `from app.models.enums import ...`, which initializes the `app.models` package and runs
  this barrel; if the barrel then asks that same half-executed module for a class, Python
  raises `cannot import name ... from partially initialized module`. The module form needs
  only the `sys.modules` entry, which exists by then, and the mappers still register on
  `Base.metadata` as the module finishes executing — which is the only thing the barrel is
  for. *Added in P3. The cycle was already latent for marketplace (P1) and verification
  (P2): it fires only when a domain model is the FIRST app module imported in a process, so
  it stayed invisible until a test happened to import one directly.* Consequences, both
  settled: classes under `app/domains/` are no longer bound on `app.models` (harmless —
  there are zero `from app.models import X` call sites; the barrel is pure alembic
  infrastructure), and `__all__` lists only what is still bound.
  > **Apply this to EVERY phase, not just the one that discovers it.** P3 fixed the four
  > barrel lines that existed then and wrote this rule down; P4-P8 each re-introduced a
  > name-import, because the mechanical path sed rewrites
  > `from app.models.x import Foo` into `from app.domains.y.models import Foo` and the
  > gate stays green — the cycle only fires when a domain model is the first app module
  > imported in a process. P8 hit it and converted all ten. After moving a model, grep
  > `^from app\.domains` in the barrel: it must return nothing.
- **Assert `Base.metadata`, not barrel attributes.** Any test checking "alembic can see this
  model" must assert `"<table>" in Base.metadata.tables`, not
  `hasattr(app.models, "<Class>")`. The latter is a proxy that the rule above breaks while
  autogenerate keeps working. One such test existed (`test_migration_0029`) and was
  converted in P3.
- `app/services/__init__.py`, `app/schemas/__init__.py`, `app/api/__init__.py` are empty — no
  existing re-export shim to lean on. **No backward-compat shims are added during this
  migration** — each domain move is atomic: move the files, update every call site (repo-wide,
  per the scan-scope finding above) in the same change, get the full gate green, then commit. Leaving old-path shim
  files would recreate the "why does this exist in two places" confusion the reorg exists to
  fix.
- A `from app.services import offer_service` (submodule-as-namespace) style is used ~62 times
  repo-wide, with call sites doing `offer_service.foo(...)`. Fix by aliasing the import
  (`from app.domains.marketplace import service as offer_service`) so call sites don't need
  touching — only the import line changes.
- CI runs two explicit directory-path mypy invocations: `mypy app/services --ignore-missing-imports`
  and `mypy app/schemas --ignore-missing-imports` (plus matching `[[tool.mypy.overrides]]` blocks
  in `backend/pyproject.toml` keyed by `app.services.*` / `app.schemas.*`). Each phase must add
  its new domain's service/schema files to these invocations — `.github/workflows/ci.yml` **and**
  the copies documented in the root and `backend/` `CLAUDE.md` — as part of that phase's change.
- **The override module keys matter as much as the invocation paths.** Global `[tool.mypy]`
  is `strict = true`, but `disallow_any_explicit` is **not** part of `strict` — it comes from
  the `app.services.*` override. A service file moved to `app/domains/` silently loses the
  explicit-`Any` ban unless a matching override exists. The settled structure, in this order
  (mypy applies the **last** matching override):
  1. `module = ["app.domains.*"]` — `disallow_untyped_defs`, `disallow_any_explicit` on.
  2. `module = ["app.domains.*.schemas", …]` — `disallow_any_explicit` **off** (the pydantic
     carve-out that `app.schemas.*` already had).
  3. `module = ["app.domains.*.models", …]` — `disallow_any_explicit` **off**.
  Block 3 was added in P3's phase: a JSONB column is `Mapped[dict[str, Any]]`, which is what
  SQLAlchemy gives you, and those models sat under no such ban in `app/models/`. **Moving a
  file between directories must not change what the type checker demands of it** — if a
  phase's mypy run reports new errors in a file it only *moved*, the override is wrong, not
  the code. Note mypy's patterns wildcard whole components, so `app.domains.*.schemas` does
  not match `portal_market_schemas` — list irregular names explicitly.
- Circular FKs exist between `companies.py`↔`verification.py` and `marketplace.py`↔`compliance.py`
  models. This does not block a folder split (FK resolution is metadata-based, not
  import-order-based) — it's accepted as a tolerated two-way relationship between those domain
  pairs, not something to solve.
- Full test suite (`pytest tests/ -q`, not a subset), `ruff check .`, and both `mypy` invocations
  must be green before every commit in this track — same standing rule as the rest of the repo.

## Test integrity across the migration (binding for every phase)

The standing rule above says the full suite must be green before every commit. **Green is not
sufficient.** These phases rewrite imports inside `tests/` as well as `app/`, so the suite is part
of the change — and a suite that is green because a test stopped running is a regression wearing a
disguise. Every phase must therefore prove *nothing broke*, not just *nothing is red*.

### Capture a baseline first, compare after every step

Before touching anything in a phase, record the numbers **in the environment you will compare in**
(they differ — locally the DB-backed tests skip for want of Postgres; on CI they run):

```bash
cd backend
uv run pytest tests/ -q --collect-only 2>&1 | tail -1   # collected / deselected
uv run pytest tests/ -q 2>&1 | tail -1                   # passed / skipped / deselected
```

Baseline at the time this section was written (local, no Postgres):
**2598 collected, 4 deselected · 1851 passed, 747 skipped.**

After each step — not only before the commit — re-run and compare. **All four numbers must be
identical.** Specifically:

- **Collected count drops** → a test file failed to import and its tests silently vanished from
  the run. Collection errors are reported, but a partial collection still exits green if the
  remaining tests pass. This is the single most likely way a phase "succeeds" while deleting
  coverage.
- **Skipped count rises** → something now skips that used to run (a missing import guarded by
  `pytest.importorskip`, a fixture that stopped resolving). A rise in skips is a failure, even
  though pytest prints it in green.
- **Passed count drops without failures** → tests moved into the skipped or deselected bucket.

Do not "fix" a mismatch by updating the baseline. Find the test that stopped running.

### Run the gate per step, not per phase

Each phase's Steps section ends with the full gate, but the gate is cheap (~80 s locally) and the
failure modes compound. Run at minimum after each of these, and fix before continuing:

1. after the `git mv` block (expect failures — this confirms *which* call sites exist),
2. after fixing internal imports within the moved files,
3. after the call-site sweep,
4. after the `app/main.py` and `pyproject.toml`/CI edits,
5. before the commit.

Step 1 is deliberately run in a broken state: the set of failures it produces is the real
call-site inventory, and it will be more accurate than any grep list written in advance.

### The 616 invisible references

`tests/` contains **616** `patch("app...")` / `setattr("app...")` target **strings**
(`app/` itself contains none). They are plain strings: ruff, mypy, IDE refactors and import
graphs are all blind to them.

Two shapes, and only one is safe:

- **Prefixed by the moved module** — e.g. `patch("app.services.request_service.write_audit")`.
  The path sed catches these.
- **Prefixed by the *consumer* module** — e.g.
  `patch("app.api.admin_settings.news_service.list_pending_news")`, which patches the name
  `news_service` *as bound inside* `admin_settings.py`. A sed keyed on `app.services.news_service`
  does **not** match this string. Where the consumer also moves (e.g.
  `patch("app.api.admin_sources.source_service.list_source_groups")`), the router-path sed fixes
  the prefix; where the consumer stays (`admin_settings.py` is shared kernel), the string stays
  valid **only because of the import-alias technique**.

Sweep them explicitly in every phase, before the commit. Two greps — the narrow one is the
check, the broad one is the safety net:

```bash
# 1. THE CHECK — must return nothing. Substitute this phase's moved module paths.
grep -rnE '(patch|setattr)\(\s*"app\.(services\.offer_service|models\.marketplace)' backend/tests

# 2. THE NET — a review list, NOT an assertion. Read it for targets whose prefix is a
#    module this phase moved.
grep -rnE '(patch|setattr)\(\s*"app\.' backend/tests | grep -vE '"app\.(core|domains)\.'

# 3. And the stale-path sweep for the phase, over the REPO ROOT (see the scan-scope
#    finding above) — not just backend/.
grep -rn --include=*.py -E '<this phase.s old module paths>' backend/app backend/tests telegram userbot
```

Grep 2 returns **525 lines today** and will never reach zero: targets prefixed
`app.api.*`, `app.tasks.*` and `app.ingest.*` are legitimate — those layers largely stay put, and
`app/tasks/` is never moved by this track at all. Do not chase it to empty. Its job is to make the
consumer-prefixed shape visible so you can spot the ones whose prefix *did* move (a router, for
instance). Grep 1 is the one that must come back clean.

Note `_patch(...)` aliases exist in the suite and are matched by both patterns — that is
intentional, not a false positive.

### Preserve import *style*, not just import paths

This is what keeps the consumer-prefixed patch targets working. `from app.services import
news_service` → `from app.domains.news import service as news_service` keeps the module object
bound to the same name, so `patch("app.api.admin_settings.news_service...")` still resolves.

Rewriting it to a direct-name import (`from app.domains.news.service import list_pending_news`)
would break that binding. If the patch target no longer exists you get a loud
`ModuleNotFoundError`; if it exists but the code under test now reads a different binding, **the
patch silently does nothing and the test passes without testing anything**. That is the one
failure mode none of the counts above will catch.

So: change import **paths**, never import **style**, and never "tidy" an import while moving it.

### Submodule-namespace imports exist on `app.api` too, not just `app.services`

The finding above documents `from app.services import offer_service`. The same shape
occurs on the router packages — `from app.api.portal import lab, lab_requests` (P7) and
`from app.api import feed as feed_module` (P10) — and a sweep that only handles
`app.services` is blind to both. Neither dotted-path sed nor the namespace rule fires;
they surface as an ImportError in whichever test happens to use them.

Grep all three package roots before moving a router:

```bash
grep -rnE "^\s*from app\.(api|api\.portal|services|models|schemas) import [a-z]" \
    backend/app backend/tests telegram userbot
```

### Parenthesized `from app.services import (...)` blocks hide from naive detectors

Every phase splits these by hand, so every phase needs to *find* them all. A detector
anchored on `^\s*from app\.services import \($` misses
`from app.services import (  # noqa: PLC0415` — the trailing comment means the line does
not end at the paren. That gap reported "0 blocks" for two real ones, and one of them
(`tests/test_escrow_notifications_db.py`, holding `deal_service` + `escrow_service`) went
stale in **P5 and stayed stale through P9**, because the test is `@requires_real_db` and
skips locally — it would only have failed on CI.

Match `^\s*from app\.services import \(` with no end anchor, and audit the whole repo
rather than only this phase's names:

```python
# every paren block whose body names ANY already-migrated service
for line in file:
    if re.match(r"^\s*from app\.services import \(", line): ...
```

Two lessons beyond the regex: a locally-skipped test is not covered by "the suite is
green", and mypy caught this one when grep did not — the `Module "app.services" has no
attribute "x"` error is worth reading carefully rather than assuming it is a stub gap.

### A moved module's `__file__`-relative paths break silently

A module that computes a path with `Path(__file__).parent.parent.parent` hard-codes how
deep it sits. Moving it one directory deeper repoints it at somewhere that does not
exist — and nothing in the gate notices, because the file it wanted is still on disk and
the test that checks for it usually computes its own path rather than asking the module.

This shipped twice: `substance_ai` (P6) and `report_service` (P8) both went a level
deeper and lost `parsing/prompts/`. `report_service._load_prompt` returns `""` for a
missing file, so reports would have rendered against an empty prompt; `substance_ai`
raises, so every AI substance suggestion would have thrown. P6's went out undetected.

Fixed at the class level in P8: `app/core/paths.py` exports `BACKEND_ROOT` and
`PROMPTS_DIR`, anchored in shared kernel that this track never moves. **Before moving any
module, grep it for `__file__`** — and if a test asserts a file exists, make it load
through the module rather than off a path it computes itself, or it will stay green while
the module is broken.

### Census before any identifier rename

A phase that renames a *symbol* (not a module path) must first list every **definition** of
that name, not just the call sites:

```bash
git grep -n "def <name>" -- 'backend/*.py'
```

*Added after P2's `deps.py` extraction.* That step moved `_company_or_404` out of
`portal/companies.py` and renamed it public. Six functions named `_company_or_404` existed —
five of them unrelated local helpers in other routers, two with a different signature
entirely — and a `\b_company_or_404\b` sweep renamed all six. Behavior survived (each file's
definition and call sites moved together) but five private helpers silently became public,
and the resulting duplicate public names were more confusing than the problem being fixed.
Caught by reading a diff, not by any gate: ruff, mypy and the suite were all green.

## Status: complete

All eleven phases have landed. `backend/app/` now holds 20 domain folders under
`app/domains/` plus an explicitly closed shared kernel, recorded in the docstrings of
`app/services/__init__.py` and `app/api/__init__.py`. "Still in `app/services/`" now
means *kernel*, not *not yet moved*.

One thing P11 floated and this track declined: collapsing the accumulated per-file mypy
arguments to `app/domains` as a directory. That directory also contains each domain's
routers, which lived in `app/api/` and were never type-gated — passing the directory
checks 177 files instead of 56 and reports ~122 explicit-Any errors in code that only
changed folder. Widening the gate to routers is a defensible thing to want, but it is a
policy decision with its own commit, not a side effect of shortening an argument list.
The reasoning is in `.github/workflows/ci.yml` next to the lists.

## Target convention

Each domain becomes `backend/app/domains/<name>/`, e.g.:
```
app/domains/marketplace/
  __init__.py
  models.py      # was app/models/marketplace.py
  schemas.py     # was app/schemas/marketplace.py
  service.py     # was app/services/offer_service.py
  compliance.py  # was app/services/offer_compliance_service.py (kept as its own file)
  requests.py    # was app/services/offer_request_service.py
  api_portal.py  # was app/api/portal/offers.py
  api_admin.py   # was app/api/offer_requests.py
```
Sub-files stay separate where the source was already meaningfully split — the goal is one
**folder** per domain, not one file per domain.

The **shared kernel** (`audit_service`, `event_service`/`event_types`, `notification_service`,
`storage_service`, `settings_service`, `app/api/deps.py`, `app/core/security.py`) stays in
`app/services/` / `app/api/` / `app/core/` — it is genuinely cross-cutting infra imported by
nearly every domain, and is not moved by this track. `app/services/` and `app/schemas/` keep
existing indefinitely, shrinking as more domains move out.

## Phase roadmap

Ordered by lowest external fan-in / least shared-kernel entanglement first (from the coupling
research), confirmed with the user:

1. **Marketplace/offers** — `P1-MARKETPLACE.md`. **DONE.** Lowest external fan-in of the two initial
   candidates (marketplace vs. verification) — no other domain's *services* reach into
   marketplace, only `offer_compliance_service` reaches out to substances/compliance. Pilot:
   establishes the folder convention, the import-alias technique, and the CI-glob pattern reused
   by every later phase.
2. **Verification** — **DONE** (`P2-VERIFICATION.md`). `verification_service`, `verification_checks`, `registry_service`,
   `otp_service`, `directory_service` + `models/verification.py`. More entangled: contracts'
   `eimzo_service` depends on it, circular FK with companies.
3. **Companies** — **DONE** (`P3-COMPANIES.md`). `company_service` + `directory_service` + `models/companies.py`. Highest fan-in (8 other domains
   depend on it) — moved once several dependents already exist as domains, so "update every call
   site" happens once at scale.
4. **Contracts** — `contract_service`, `contract_render`, `eimzo_service`.
5. **Deals/Escrow/RFQ** — `deal_service`, `escrow_service`, `rfq_response_service`,
   `rfq_push_service`, `supplier_matching_service`.
6. **Compliance/Substances** — `substance_service`, `substance_ai_service`,
   `company_license_service`.
7. **Lab/Logistics/Manufacturers** — `lab_service`, `laboratory_service`, `logistics_service`,
   `manufacturer_service`, `sample_service`.
8. **News/Reports** — **DONE** (`P8-NEWS-REPORTS.md`). `news_service`, `news_dedup`, `report_service`, `ai_signal_service`,
   `relevance_service`, `grade_service`.
9. **Requests/Pricing** — **DONE** (`P9-REQUESTS-PRICING.md`, two folders). `request_service`, `request_analysis_service`, `price_analysis_service`,
   `dashboard_summary_service`.
10. **Signals/Ingest** — **DONE** (`P10-SIGNALS-SOURCING.md`, signals + sourcing). `signal_service`, `raw_pipeline`, `source_service`,
    `source_health_service`, `sourcing_service` (`app/ingest/` adapter package already has its
    own per-type structure and is left as-is).
11. **DONE** (`P11-REMAINDER.md`). Remaining small isolated services (`alert_service`, `auth_service`, `client_service`,
    `fx_service`, `lead_score_recompute_service`, `rate_limit`, `review_service`,
    `userbot_health_service`, `product_service`) grouped into 2-3 small domains at the end.

Each phase gets its own `P<N>-<NAME>.md` in this directory, written just before that phase
starts — not drafted all up front, so later plans don't drift from the codebase before they're
executed. Plain hand-written Markdown; no GSD tooling (removed from this project).
