---
phase: 02-ingest-core-uzex
reviewed: 2026-06-16T07:00:00Z
depth: standard
files_reviewed: 27
files_reviewed_list:
  - backend/alembic/versions/0002_synonyms_and_classification_queue.py
  - backend/app/api/admin_sources.py
  - backend/app/core/config.py
  - backend/app/ingest/base.py
  - backend/app/ingest/cbu_rates/adapter.py
  - backend/app/ingest/http_client.py
  - backend/app/ingest/registry.py
  - backend/app/ingest/uzex/adapters.py
  - backend/app/ingest/uzex/parse_tables.py
  - backend/app/main.py
  - backend/app/models/reference.py
  - backend/app/seed/seed_reference.py
  - backend/app/seed/seed_sources.py
  - backend/app/services/fx_service.py
  - backend/app/services/grade_service.py
  - backend/app/services/raw_pipeline.py
  - backend/app/services/relevance_service.py
  - backend/app/services/signal_service.py
  - backend/app/services/source_health_service.py
  - backend/app/tasks/celery_app.py
  - backend/app/tasks/ingest.py
  - backend/app/tasks/ingest_cbu.py
  - backend/app/tasks/notify.py
  - backend/app/tasks/parse.py
  - backend/app/tasks/placeholders.py
  - backend/app/tasks/schedule.py
  - deploy/backup/pg_backup.sh
findings:
  critical: 4
  warning: 7
  info: 3
  total: 14
status: issues_found
---

# Phase 02: Ingest Core + UZEX — Code Review Report

**Reviewed:** 2026-06-16T07:00:00Z
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

Phase 02 implements the ingest pipeline for UZEX trade data and CBU FX rates, the Celery task infrastructure, the raw-item dedup pipeline, and the relevance/grade/signal services. The overall architecture is sound: bound-parameter SQL is used consistently, Decimal math is correctly applied for money values, the parse-status machine is coherent, and admin authorization is properly wired.

Four blockers were found:

1. **SSRF bypass via HTTP redirect** — the SSRF DNS pre-check is bypassed by any HTTP 301/302 redirect to an internal IP because `follow_redirects=True` is set and no post-redirect re-validation occurs.
2. **SSRF gap: RFC 6598 CGNAT range not blocked** — `100.64.0.0/10` is not `is_private`, `is_reserved`, or any other blocked category in Python's `ipaddress` module; an attacker-controlled source config can reach CGNAT-hosted internal services.
3. **Task name collision — placeholders.py is always loaded and wins** — both `placeholders.py` and the real implementation modules define tasks under the same Celery name strings. Because Celery autodiscovery order is not guaranteed (alphabetically `ingest.py` > `placeholders.py` when sorted, but that depends on discovery order), the placeholder definitions risk silently winning in some deployment configurations, causing every scheduled task to return `status: not_yet_implemented` with no error.
4. **`_enqueue_parse_tasks` race: enqueues items from previous runs** — the function queries `parse_status='pending'` with `ORDER BY fetched_at DESC LIMIT :count` after a commit; it relies on recency ordering to find only the items just inserted. On a busy source where a prior batch is still pending, the LIMIT can select old items (still pending) instead of the new ones, leading to parse tasks being sent for items that were already enqueued or re-enqueuing items whose tasks are already in flight.

Seven warnings cover: `date.today()` timezone inconsistency in alert deduplication, `ccy_allowlist` config field silently ignored, open `/docs` and `/redoc` without auth guard, `ls` pipeline for backup pruning that silently misses filenames with spaces/newlines, `grade_text` lookup against an empty field for UZEX feeds, and two session-lifecycle issues in `ingest.py`.

---

## Critical Issues

### CR-01: SSRF bypass via HTTP redirect — `follow_redirects=True` without post-redirect IP re-validation

**File:** `backend/app/ingest/http_client.py:194`

**Issue:** `is_safe_url()` resolves the DNS name of the *original* URL before the request is made. If the server returns an HTTP 3xx redirect pointing to `http://169.254.169.254/` (AWS metadata) or any RFC 1918 address, `httpx` silently follows it because `follow_redirects=True` is set. The post-redirect target is never passed through `is_safe_url()`, so the SSRF guard is completely bypassed by any public server that issues an internal redirect. This is a standard SSRF bypass technique documented in CVE-2021-41945 class vulnerabilities.

**Fix:** Either (a) disable redirects and require sources to use direct URLs, or (b) hook the redirect event to re-check each intermediate URL:

```python
# Option A (recommended — simplest, no redirect needed for trusted sources):
async with httpx.AsyncClient(
    timeout=httpx.Timeout(timeout),
    follow_redirects=False,   # <-- disable
    headers=headers,
) as client:
    ...

# Option B — validate every redirect target before following:
class _SSRFCheckTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not is_safe_url(str(request.url)):
            raise ValueError(f"SSRF guard: redirect target {request.url!r} rejected")
        return await super().handle_async_request(request)

async with httpx.AsyncClient(
    transport=_SSRFCheckTransport(),
    follow_redirects=True,
    ...
) as client:
    ...
```

---

### CR-02: SSRF gap — RFC 6598 CGNAT range `100.64.0.0/10` passes `_is_private_ip()` check

**File:** `backend/app/ingest/http_client.py:118-130`

**Issue:** Python's `ipaddress` module does not classify `100.64.0.0/10` (RFC 6598 shared address space / CGNAT) as `is_private`, `is_loopback`, `is_link_local`, `is_reserved`, `is_unspecified`, or `is_multicast`. Verified in Python 3.12:

```
100.64.0.1: private=False loopback=False link_local=False reserved=False multicast=False global=False
```

Any attacker who can control a source's `endpoint_url` (e.g., via the admin source constructor) can direct the worker to fetch from an IP in this range. In cloud environments (AWS, GCP, Azure) where CGNAT is used for internal VPCs or internal load balancers, this bypasses the SSRF guard entirely.

**Fix:** Add an explicit CIDR check for RFC 6598:

```python
import ipaddress

_SSRF_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.IPv4Network("100.64.0.0/10"),   # RFC 6598 — CGNAT/shared address space
    # Add any other site-specific ranges as needed
)

def _is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    ):
        return True
    # Explicit check for ranges not covered by the above
    for net in _SSRF_BLOCKED_NETWORKS:
        if ip in net:
            return True
    return False
```

---

### CR-03: Placeholder Celery tasks can silently win over real implementations

**File:** `backend/app/tasks/placeholders.py:33-80` / `backend/app/tasks/ingest.py:224-254` / `backend/app/tasks/celery_app.py:82`

**Issue:** Both `placeholders.py` and the real modules (`ingest.py`, `ingest_cbu.py`, `notify.py`) register tasks under identical name strings (`uzex_fetch_offers`, `uzex_fetch_contracts`, `uzex_fetch_deals`, `fetch_cbu_rates`, `check_source_health`). The code comment says "last registration wins during autodiscovery — Celery resolves by name, not by module," but this is only true if the real implementations are always imported *after* the placeholders.

`celery_app.autodiscover_tasks(["app.tasks"])` scans the `app.tasks` package directory. Python's `importlib` and `pkgutil.walk_packages` do not guarantee alphabetical import order in all CPython versions and all filesystem types. On case-insensitive or unsorted filesystems, `placeholders.py` can be imported after `ingest.py`, causing the placeholder definition to overwrite the real one. In production the symptom is silent: every UZEX fetch cron returns `status: not_yet_implemented` but no exception is raised so the task appears healthy.

**Fix:** Delete `placeholders.py` entirely now that the real implementations exist. The placeholders were scaffolding for wave sequencing; they are now dead weight with an active safety hazard.

```bash
git rm backend/app/tasks/placeholders.py
```

If the file must be retained for compatibility, rename each placeholder task to a unique name that does not conflict with the contract names:

```python
@celery_app.task(name="_placeholder_uzex_fetch_offers")
def placeholder_uzex_fetch_offers() -> dict[str, Any]: ...
```

---

### CR-04: `_enqueue_parse_tasks` uses an unreliable heuristic to find newly inserted rows

**File:** `backend/app/tasks/ingest.py:194-218`

**Issue:** After `save_raw_items()` inserts `N` new rows and the session is committed, `_enqueue_parse_tasks` runs:

```sql
SELECT id FROM raw_items
WHERE source_id = :sid AND parse_status = 'pending'
ORDER BY fetched_at DESC
LIMIT :lim
```

This query assumes the `N` most-recently-fetched pending rows for this source are the ones just inserted. This assumption is false in two real scenarios:

1. **Previous batch still pending:** If the prior ingest run for this source produced items whose parse tasks are still in the `parse` queue (not yet consumed), those rows remain `parse_status='pending'`. The LIMIT will include them, and the same `parse_raw_item` task will be enqueued *again* for the same row IDs. The double-parse guard in `parse.py` protects against producing duplicate signals, but parse queue depth grows without bound.

2. **Clock/insert ordering:** `fetched_at` is a `server_default=func.now()` set by the DB. If the DB and worker clocks drift, the ordering is not strictly correlated with insertion order within the same transaction.

The correct approach is to return the inserted IDs from `save_raw_items` so the enqueue call uses exact IDs rather than a proximity query.

**Fix:** Extend `save_raw_items` to return the list of inserted IDs and pass them directly to the enqueue function:

```python
# In raw_pipeline.py — return inserted IDs
def save_raw_items(session, source, drafts) -> tuple[int, list[int]]:
    ...
    inserted_ids: list[int] = []
    for draft in drafts:
        ...
        cursor = session.execute(...)
        if getattr(cursor, "rowcount", 0) == 1:
            # PostgreSQL RETURNING id
            row = cursor.fetchone()
            if row:
                inserted_ids.append(row[0])
    return len(inserted_ids), inserted_ids

# In ingest.py
inserted, inserted_ids = save_raw_items(session, source, drafts)
...
for raw_item_id in inserted_ids:
    celery_app.send_task("parse_raw_item", args=[raw_item_id], queue="parse")
```

Alternatively add `RETURNING id` to the existing INSERT in `raw_pipeline.py`.

---

## Warnings

### WR-01: `date.today()` uses local system timezone for alert dedup key — can create double alerts at midnight UTC

**File:** `backend/app/services/source_health_service.py:147`

**Issue:** `datetime.date.today()` returns the *system-local* date, not UTC. The rest of the service uses `datetime.datetime.now(tz=datetime.UTC)` correctly. If the server's `TZ` environment variable is set to `Asia/Tashkent` (UTC+5), `date.today()` on a night straddling 19:00–24:00 UTC will return a date one day ahead of what a UTC-based observer sees. Two alert inserts in the same UTC calendar day but across the local midnight boundary will produce different `dedupe_key` strings (`source_failure:1:2026-06-15` vs `source_failure:1:2026-06-16`), allowing two alerts to fire for the same source on the same UTC day.

**Fix:**
```python
# Replace:
today = datetime.date.today().isoformat()
# With:
today = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
```

---

### WR-02: `ccy_allowlist` config field is declared but never enforced

**File:** `backend/app/ingest/cbu_rates/adapter.py:68`

**Issue:** `CbuRatesConfig.ccy_allowlist` is advertised to admins via the `GET /admin/source-types` schema and documented as `"empty = accept all currencies"`. However, neither `_parse_cbu_json()` nor `fetch()` reads this field. An admin who configures `ccy_allowlist: ["USD", "CNY"]` expecting to filter rates will receive all ~70 CBU currencies silently. The mismatch between the config schema and runtime behavior is a functional bug, and the field is a deceptive API surface.

**Fix:** Either enforce the allowlist in `_parse_cbu_json` or `fetch`, or remove the field from `CbuRatesConfig` until it is implemented:

```python
# Minimal enforcement in fetch():
async def fetch(self, source: Source) -> list[RawItemDraft]:
    config = source.config or {}
    endpoint_url = str(config.get("endpoint_url", _CBU_DEFAULT_URL))
    allowlist: list[str] = [str(c).upper() for c in (config.get("ccy_allowlist") or [])]

    response = await fetch_url(endpoint_url)
    rows = self._parse_cbu_json(response.text)

    if allowlist:
        rows = [r for r in rows if r.ccy in allowlist]
    ...
```

---

### WR-03: `/docs` and `/redoc` exposed without authentication in production

**File:** `backend/app/main.py:73-74`

**Issue:** `FastAPI` is configured with `docs_url="/docs"` and `redoc_url="/redoc"` without any authentication guard. The OpenAPI schema enumerates all endpoints (including their request/response models and security requirements), which aids enumeration attacks. REQ-nfr-security states "no secret literals in tracked source" but does not protect against schema leakage. A production deployment with these docs enabled provides an attacker with a complete, up-to-date map of the attack surface.

**Fix:** Disable the docs endpoints or gate them behind a header/IP check for production environments:

```python
application = FastAPI(
    ...
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)
```

Add a `DEBUG: bool = False` setting to `config.py`.

---

### WR-04: `ls` pipeline in pg_backup.sh is not robust against filenames with spaces or newlines

**File:** `deploy/backup/pg_backup.sh:82-91`

**Issue:** The retention pruning loop uses:
```bash
ls -1t "${DAILY_DIR}"/*.pgdump 2>/dev/null | tail -n "+$((DAILY_KEEP + 1))" | while read -r OLD; do
    rm -f "${OLD}"
done
```

`ls` output is split on newlines, so a `.pgdump` filename containing a newline character (possible if `PGDATABASE` or `TIMESTAMP` are injected with unusual values) will silently delete only part of the filename or delete the wrong file. More practically: if `BACKUP_DIR` itself contains a space, the glob `"${DAILY_DIR}"/*.pgdump` expands incorrectly despite quoting, because the glob is evaluated in a subshell context passed to `ls` as a positional argument.

Safer alternative using `find` + `sort`:

```bash
# Daily pruning — robust version
mapfile -t DAILY_FILES < <(find "${DAILY_DIR}" -maxdepth 1 -name '*.pgdump' -printf '%T@ %p\0' | sort -rz -k1,1 | sed -z 's/^[^ ]* //')
for OLD in "${DAILY_FILES[@]:${DAILY_KEEP}}"; do
    echo "[pg_backup] Removing old daily backup: ${OLD}"
    rm -f -- "${OLD}"
done
```

Or use `find -delete` with a time-based filter rather than relying on count + `ls` ordering.

---

### WR-05: Grade extraction in `parse_raw_item` looks up `grade_text` payload key — field is never populated by UZEX adapters

**File:** `backend/app/tasks/parse.py:135-136`

**Issue:** The parse task extracts grade information with:
```python
grade_text_raw = str(payload.get("grade_text", "")).strip()
grade_id, grade_text = extract_grade(grade_text_raw, session)
```

However, the UZEX adapter column configs (`UzexOffersConfig`, `UzexContractsConfig`, `UzexDealsConfig` in `adapters.py`) do not include `grade_text` in their `columns` lists. The `product_text` column typically contains the full description including grade (e.g., `"ПП T30S Шуртан"`). `grade_text_raw` will always be an empty string for UZEX sources, so `extract_grade("", session)` always returns `(None, None)` immediately (short-circuited at the `if not text_:` guard in `grade_service.py`). Grade linking is silently dead for the UZEX ingest path.

The grade should be extracted from `product_text` rather than from a separate (absent) `grade_text` field:

```python
# Replace:
grade_text_raw = str(payload.get("grade_text", "")).strip()
# With: fall back to product_text when grade_text is absent
grade_text_raw = (
    str(payload.get("grade_text", "")).strip()
    or str(payload.get("product_text", "")).strip()
)
grade_id, grade_text = extract_grade(grade_text_raw, session)
```

---

### WR-06: Session is reused across sources after rollback in `run_source_fetch_isolated` — health record may silently fail

**File:** `backend/app/tasks/ingest.py:115-130`

**Issue:** On an exception, the code does:
```python
with contextlib.suppress(Exception):
    session.rollback()

record_fetch_failure(session, source.id, str(exc))
with contextlib.suppress(Exception):
    session.commit()
```

After `session.rollback()`, the session state is clean but the `source` ORM object that was originally loaded is now *expired* (SQLAlchemy expires all objects on rollback in default configuration). Accessing `source.id` after a rollback is safe only because `.id` is the primary key and is already in the instance's identity — but if `record_fetch_failure` itself raises an exception (e.g., the DB is unreachable), the outer `contextlib.suppress(Exception)` silently swallows the failure. The source health counter is not incremented, and the task returns `0` with no indication that health tracking failed.

The `contextlib.suppress(Exception)` around `record_fetch_failure` is too broad. A suppressed DB failure here means the 3-consecutive-failure threshold is never reached and no alert fires.

**Fix:** Log a critical-level warning on suppressed health-recording failures so they are at least visible in observability tooling:

```python
try:
    record_fetch_failure(session, source.id, str(exc))
    session.commit()
except Exception as health_exc:
    logger.critical(
        "uzex_fetch.health_record_failed",
        extra={"source_id": source.id, "error": str(health_exc)},
    )
```

---

### WR-07: `fetch_cbu_rates` task ignores `source.config.endpoint_url` — always fetches from hardcoded URL

**File:** `backend/app/tasks/ingest_cbu.py:125-134`

**Issue:** The `_fetch_cbu_body` helper fetches from `_CBU_DEFAULT_URL` unconditionally, ignoring any `endpoint_url` set in the source row's config:

```python
async def _fetch_cbu_body(adapter: object) -> str:
    from app.ingest.cbu_rates.adapter import _CBU_DEFAULT_URL
    from app.ingest.http_client import fetch_url
    response = await fetch_url(_CBU_DEFAULT_URL)  # <-- always default URL
    return response.text
```

The adapter's own `fetch()` and `test()` methods correctly read `config.get("endpoint_url", _CBU_DEFAULT_URL)`, but the Celery task bypasses them entirely and calls the private `_parse_cbu_json` directly after fetching from the hardcoded URL. This means an admin cannot override the endpoint URL via source config — the feature is documented in `CbuRatesConfig` but silently non-functional in the scheduled task path.

**Fix:** Use the adapter's `fetch()` method (which reads the config) rather than a separate helper:

```python
@celery_app.task(name="fetch_cbu_rates")
def fetch_cbu_rates() -> dict[str, Any]:
    ...
    with Session(engine) as session:
        source_row = session.execute(...).fetchone()
        source_id = source_row[0] if source_row else None

    # Use adapter.fetch() which correctly reads source.config
    if source_id is not None:
        with Session(engine) as session:
            source = session.get(Source, source_id)
            drafts = asyncio.run(adapter.fetch(source))
            rate_rows = [_draft_to_cbu_row(d) for d in drafts]
    else:
        rate_rows = asyncio.run(_fetch_default_rates(adapter))
```

Or simply call `asyncio.run(adapter.test(config))` and parse the result.

---

## Info

### IN-01: `_load_enabled_sources` mixes ORM and raw-text filter — fragile pattern

**File:** `backend/app/tasks/ingest.py:48-60`

**Issue:**
```python
session.query(Source)
    .filter(sa.text("adapter = :adapter AND is_enabled = true"))
    .params(adapter=adapter_name)
    .all()
```

Using `sa.text()` inside an ORM `.filter()` bypasses column-name validation and breaks if the table or column is renamed. The project pattern elsewhere (services layer) uses ORM attributes or bound-parameter `text()` queries. This should use ORM-style filter predicates for consistency and refactoring safety:

```python
from app.models.sources import Source
session.query(Source).filter(
    Source.adapter == adapter_name,
    Source.is_enabled == True,  # noqa: E712
).all()
```

---

### IN-02: `errors` key in `_execute_uzex_fetch` return dict is always an empty list

**File:** `backend/app/tasks/ingest.py:188-191`

**Issue:** The returned dict includes `"errors": []` but error reporting is handled entirely inside `run_source_fetch_isolated` (which logs and records via `record_fetch_failure`). The `errors` key is never populated. Callers that inspect this field (e.g., monitoring integrations) will never see source-level errors in the return value. Either populate it or remove the key to avoid misleading consumers.

---

### IN-03: `product_synonyms` migration index is not `UNIQUE` — redundant given the unique constraint

**File:** `backend/alembic/versions/0002_synonyms_and_classification_queue.py:59-63`

**Issue:** The migration creates both a `UniqueConstraint("synonym_norm", ...)` and a separate non-unique `create_index("ix_product_synonyms_norm", ...)`. In PostgreSQL, a UNIQUE constraint automatically creates a unique index, making the separate `ix_product_synonyms_norm` index redundant — it covers the same column with identical access characteristics but is a second index consuming extra storage and write overhead.

**Fix:** Remove the separate index creation (the unique constraint's implicit index is sufficient and the optimizer will use it for equality lookups):

```python
# Remove this block from upgrade():
op.create_index(
    "ix_product_synonyms_norm",
    "product_synonyms",
    ["synonym_norm"],
)
# And its corresponding drop_index() in downgrade()
```

---

_Reviewed: 2026-06-16T07:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
