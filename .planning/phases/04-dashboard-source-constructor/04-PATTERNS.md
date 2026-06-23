# Phase 4: Dashboard + Source Constructor — Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 29 (13 backend, 16 frontend)
**Analogs found:** 22 / 29 (7 files have no in-repo analog — noted explicitly)

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `backend/app/api/feed.py` | router | request-response + streaming | `backend/app/api/admin_sources.py` | role-match |
| `backend/app/api/dashboard_requests.py` | router | CRUD + request-response | `backend/app/api/webapp/requests.py` | exact |
| `backend/app/api/signals.py` | router | CRUD | `backend/app/api/webapp/requests.py` | role-match |
| `backend/app/api/prices.py` | router | request-response | `backend/app/api/admin_sources.py` | role-match |
| `backend/app/api/sources.py` | router | CRUD | `backend/app/api/admin_sources.py` | exact |
| `backend/app/api/alert_rules.py` | router | CRUD | `backend/app/api/admin_sources.py` | role-match |
| `backend/app/api/admin_users.py` | router | request-response | `backend/app/api/admin_sources.py` | role-match |
| `backend/app/services/alert_service.py` | service | event-driven | `backend/app/services/request_service.py` | role-match |
| `backend/app/services/request_service.py` (extend) | service | CRUD | self | exact |
| `backend/app/ingest/html_table/adapter.py` | adapter | request-response | `backend/app/ingest/uzex/adapters.py` | exact |
| `backend/app/ingest/rss/adapter.py` | adapter | request-response | `backend/app/ingest/uzex/adapters.py` | exact |
| `backend/app/ingest/telegram_channel/adapter.py` | adapter | stub | `backend/app/ingest/uzex/adapters.py` | role-match |
| `backend/app/ingest/llm_page/adapter.py` | adapter | stub | `backend/app/ingest/uzex/adapters.py` | role-match |
| `backend/tests/test_feed_api.py` | test | — | `backend/tests/test_webapp_requests_api.py` | exact |
| `backend/tests/test_dashboard_requests.py` | test | — | `backend/tests/test_webapp_requests_api.py` | exact |
| `backend/tests/test_alert_service.py` | test | — | `backend/tests/test_request_service.py` | role-match |
| `backend/tests/test_source_wizard.py` | test | — | `backend/tests/test_admin_source_types.py` | exact |
| `dashboard/app/(dashboard)/layout.tsx` | layout | request-response | `dashboard/app/layout.tsx` | role-match |
| `dashboard/app/(dashboard)/page.tsx` | component | CRUD | `dashboard/app/login/page.tsx` | role-match |
| `dashboard/components/layout/Sidebar.tsx` | component | — | `dashboard/app/login/page.tsx` | partial (token patterns only) |
| `dashboard/hooks/useSSE.ts` | hook | streaming | no analog | none |
| `dashboard/hooks/useAuth.ts` | hook | request-response | `dashboard/app/login/page.tsx` | partial |
| `dashboard/lib/api.ts` | utility | request-response | no analog | none |
| `dashboard/lib/queryClient.ts` | config | — | no analog | none |
| `dashboard/lib/tz.ts` | utility | transform | no analog | none |
| `dashboard/components/sources/JsonSchemaForm.tsx` | component | transform | no analog | none |
| `dashboard/components/requests/RequestDetailPanel.tsx` | component | CRUD | `dashboard/app/login/page.tsx` | partial (token patterns only) |
| `dashboard/components/requests/AiAnalysisBlock.tsx` | component | — | `dashboard/app/login/page.tsx` | partial (token patterns only) |
| `dashboard/components/prices/PriceChart.tsx` | component | request-response | `dashboard/app/login/page.tsx` | partial (token patterns only) |

---

## Pattern Assignments

### `backend/app/api/feed.py` (router, request-response + streaming)

**Analog:** `backend/app/api/admin_sources.py`

**Imports pattern** (`admin_sources.py` lines 19–32):
```python
from __future__ import annotations

import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.db import get_db
from app.models.staff import StaffUser
```

**Auth guard pattern** (`deps.py` lines 107–138) — use `get_current_staff_user` for all-staff endpoints, `require_role(...)` for restricted ones:
```python
from app.api.deps import get_current_staff_user, require_role
from app.models.enums import StaffRole

# All-staff read:
_: StaffUser = Depends(get_current_staff_user)

# Role-restricted write:
_: StaffUser = Depends(require_role(StaffRole.admin, StaffRole.analyst))
```

**Core GET list pattern** (`admin_sources.py` lines 57–88) — router definition + Depends auth + SA query:
```python
router = APIRouter(prefix="/feed", tags=["feed"])

@router.get("/", response_model=list[FeedItem])
def get_feed(
    cursor_event_at: datetime.datetime | None = None,
    cursor_id: int | None = None,
    limit: int = Query(default=50, le=200),
    kind: str | None = None,
    product_id: int | None = None,
    db: Session = Depends(get_db),
    _: StaffUser = Depends(get_current_staff_user),
) -> list[FeedItem]:
    rows = db.execute(sa.text("""..."""), {...}).fetchall()
    return [FeedItem(...) for row in rows]
```

**SSE streaming pattern** (RESEARCH.md Pattern 2, lines 389–401 — no codebase analog):
```python
from fastapi.responses import StreamingResponse
import asyncio

@router.get("/stream")
async def feed_stream(_: StaffUser = Depends(get_current_staff_user)):
    async def event_generator():
        # Redis pub/sub or periodic-poll watermark approach
        async with redis_pubsub.subscribe("feed:new") as sub:
            async for message in sub:
                yield f"data: {message}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

**Keyset pagination pattern** (RESEARCH.md Pattern 1, lines 291–318):
```python
# WHERE clause for (event_at, id) cursor — avoids OFFSET
# Requires composite index on underlying tables (verified: signals has it)
WHERE (:cursor_ea IS NULL
       OR event_at < :cursor_ea
       OR (event_at = :cursor_ea AND id < :cursor_id))
ORDER BY event_at DESC, id DESC
LIMIT :limit
```

---

### `backend/app/api/dashboard_requests.py` (router, CRUD)

**Analog:** `backend/app/api/webapp/requests.py` (lines 1–149)

**Imports pattern** (lines 18–27):
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff_user, require_role
from app.core.db import get_db
from app.models.requests import Request
from app.models.enums import RequestStatus, StaffRole
from app.schemas.dashboard import RequestListOut, RequestDetailOut, RequestPatch
from app.services import request_service
```

**GET list pattern** (`webapp/requests.py` lines 66–87) — staff-scoped list using ORM query:
```python
@router.get("/requests", response_model=list[RequestListOut])
def list_requests(
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(get_current_staff_user),
) -> list[RequestListOut]:
    requests = (
        db.query(Request)
        .order_by(Request.created_at.desc())
        .all()
    )
    return requests
```

**GET detail pattern** (`webapp/requests.py` lines 90–149) — 404 guard + relationship load:
```python
@router.get("/requests/{request_id}", response_model=RequestDetailOut)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(get_current_staff_user),
) -> RequestDetailOut:
    req: Request | None = db.query(Request).filter(Request.id == request_id).first()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    # auto-transition new → viewed
    if req.status == RequestStatus.new:
        request_service.transition_status(db, req, RequestStatus.viewed,
                                          changed_by=current_user.id)
        db.commit()
    return req
```

**PATCH + status machine pattern** — call service, catch ValueError → 422, commit in router:
```python
@router.patch("/requests/{request_id}", response_model=RequestDetailOut)
def patch_request(
    request_id: int,
    body: RequestPatch,
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(require_role(StaffRole.admin, StaffRole.analyst, StaffRole.trader)),
) -> RequestDetailOut:
    req = db.query(Request).filter(Request.id == request_id).first()
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    try:
        if body.status is not None:
            request_service.transition_status(db, req, body.status,
                                              changed_by=current_user.id)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return req
```

**Audit pattern for note / assign / contact** — `audit_service.write_audit` + `db.flush()` + caller commits (`audit_service.py` lines 23–60):
```python
from app.services.audit_service import write_audit

# Inside the action handler, BEFORE db.commit():
write_audit(
    db=db,
    staff_user_id=current_user.id,
    action="request.add_note",          # or "request.assign_owner", "request.contact_buyer"
    entity="requests",
    entity_id=str(request_id),
    details={"note": body.note},
)
# db.flush() is called inside write_audit — do NOT call db.commit() in the service
db.commit()  # router owns the commit
```

---

### `backend/app/api/sources.py` (router, CRUD)

**Analog:** `backend/app/api/admin_sources.py` (lines 1–159)

**Imports + router prefix** (lines 19–33):
```python
from __future__ import annotations

import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_admin, get_current_staff_user
from app.core.db import get_db
from app.models.staff import StaffUser

router = APIRouter(prefix="/sources", tags=["sources"])
```

**Health-only response model** (`admin_sources.py` lines 95–109) — never expose `config` field:
```python
class SourceHealthItem(BaseModel):
    id: int
    name: str
    adapter: str
    kind: str
    is_enabled: bool
    last_fetch_at: datetime.datetime | None
    last_success_at: datetime.datetime | None
    consecutive_failures: int
    last_test_ok_at: datetime.datetime | None   # Phase 4 addition for enable-gate UI
```

**SA raw query for list** (`admin_sources.py` lines 136–158) — never ORM-load config column:
```python
rows = db.execute(
    sa.text("""
        SELECT id, name, adapter, kind::text, is_enabled,
               last_fetch_at, last_success_at, consecutive_failures, last_test_ok_at
        FROM sources
        ORDER BY id
    """)
).fetchall()
```

**Enable-gate invariant** (RESEARCH.md Pattern 6, lines 613–648):
```python
@router.patch("/{source_id}", response_model=SourceHealthItem)
def patch_source(
    source_id: int,
    body: SourcePatch,
    db: Session = Depends(get_db),
    _: StaffUser = Depends(require_admin),
):
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    if body.is_enabled is True and source.last_test_ok_at is None:
        raise HTTPException(
            status_code=422,
            detail="Source cannot be enabled until a test has passed successfully."
        )

    if body.is_enabled is not None:
        source.is_enabled = body.is_enabled
    db.commit()
    return source
```

**Test endpoint pattern** (RESEARCH.md Pattern 6, lines 638–648):
```python
@router.post("/{source_id}/test")
async def test_source(
    source_id: int,
    db: Session = Depends(get_db),
    _: StaffUser = Depends(require_admin),
):
    from app.ingest.registry import get_adapter  # lazy import
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    adapter = get_adapter(source.adapter)
    result = await adapter.test(source.config)
    if result.ok:
        source.last_test_ok_at = datetime.datetime.now(tz=datetime.UTC)
        db.commit()
    return {"ok": result.ok, "sample_rows": result.sample_rows, "error": result.error}
```

---

### `backend/app/api/alert_rules.py` (router, CRUD)

**Analog:** `backend/app/api/admin_sources.py` (role-match — same admin-only pattern)

**Auth guard:** `require_admin` for write endpoints (POST/PATCH), `get_current_staff_user` for GET.

**CRUD pattern** — same as `admin_sources.py`: `BaseModel` response schema, SA query or ORM get, `db.add()` + `db.commit()` in router. No `db.commit()` inside service layer.

**Delivery channel structure** in rule body (RESEARCH.md Pattern 3):
```python
class AlertRuleCreate(BaseModel):
    name: str
    condition: dict   # hardcoded predicate set keys only
    channels: list[dict]  # [{"type": "telegram_dm", "chat_id": -1001234567890}]
    is_enabled: bool = True
```

---

### `backend/app/api/admin_users.py` (router, request-response)

**Analog:** `backend/app/api/admin_sources.py` (exact same structure — admin-only GET list)

**Pattern:** Copy `admin_sources.py` router setup. Replace the SA query to select from `staff_users`. Response model exposes only `id, email, role, is_active, created_at` — never `password_hash`.

```python
router = APIRouter(prefix="/admin", tags=["admin-users"])

@router.get("/users", response_model=list[StaffUserItem])
def get_users(
    _current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[StaffUserItem]:
    rows = db.execute(
        sa.text("SELECT id, email, role::text, is_active, created_at FROM staff_users ORDER BY id")
    ).fetchall()
    return [StaffUserItem(...) for row in rows]
```

---

### `backend/app/api/signals.py` + `backend/app/api/prices.py`

**Analog:** `backend/app/api/webapp/requests.py` (role-match — GET list + optional GET detail)

Both follow the same pattern as `dashboard_requests.py`: `APIRouter`, `get_current_staff_user` dep, SA text query or ORM `.query()`, Pydantic response model. Prices adds SQL-level downsampling for `>1yr` ranges per RESEARCH.md Pattern 1 comment.

---

### `backend/app/services/alert_service.py` (service, event-driven)

**Analog:** `backend/app/services/request_service.py` (role-match — same `db.flush()` / no commit / audit pattern)

**Key pattern — service-never-commits** (`request_service.py` lines 1–23):
```python
# Service-never-commits axiom (DEC-dep-owns-commit):
# All functions call db.flush() to obtain generated IDs but NEVER call commit().
# The router (or Celery task wrapper) owns the commit.
```

**JSONB predicate interpreter core** (RESEARCH.md Pattern 3, lines 419–500):
```python
def evaluate_condition(condition: dict, entity) -> bool:
    """Hardcoded interpreter. Never uses eval()."""
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
        # Phase 4: lead_score is always None — predicate never matches (D-07)
        lead_score = (entity.ai or {}).get("lead_score")
        if lead_score is None or lead_score < condition["lead_score_gte"]:
            return False
    return True
```

**Delivery dispatch + dedupe pattern** (RESEARCH.md Pattern 3, lines 453–501) — uses `db.flush()` + `IntegrityError` catch for `ON CONFLICT(dedupe_key)`:
```python
from sqlalchemy.exc import IntegrityError

dedupe_key = f"rule:{rule.id}:{entity_type}:{entity_id}"
alert = Alert(..., dedupe_key=dedupe_key)
db.add(alert)
try:
    db.flush()
except IntegrityError:
    db.rollback()
    continue  # duplicate — already alerted

# Enqueue on the existing notify queue (D-09 — same queue as Phase 3)
from app.tasks.notify import send_delivery  # lazy import
send_delivery.apply_async(args=[alert.id], queue="notify")
```

**Lazy import pattern for Celery tasks** (`request_service.py` lines 207–209 and 279–281):
```python
# Always import Celery tasks lazily inside the function body to avoid
# circular imports and keep module import socket-free (pytest-safe)
from app.tasks.notify import send_status_change_notification  # noqa: PLC0415
send_status_change_notification.apply_async(args=[req.id], queue="notify")
```

---

### `backend/app/services/request_service.py` (extend existing — Phase 4 additions)

**File exists.** Add three new functions alongside `transition_status`:

1. `add_note(db, request_id, note_text, staff_user_id)` — inserts into `request_notes` (or `audit_log` details), calls `write_audit`, no commit.
2. `assign_owner(db, request, staff_user_id, changed_by)` — sets `request.assigned_to`, calls `write_audit`, no commit.
3. `log_contact_buyer(db, request, staff_user_id)` — calls `transition_status` to `in_progress` if `new/viewed`, writes audit with `action="request.contact_buyer"`, no commit.

Follow existing `transition_status` signature exactly (`request_service.py` lines 218–292): accept `db`, entity object, acting user id; call `write_audit`; call `db.flush()`; never `db.commit()`.

---

### `backend/app/ingest/html_table/adapter.py` + `rss/adapter.py` (adapters, request-response)

**Analog:** `backend/app/ingest/uzex/adapters.py` (exact — same Protocol structure)

**Config schema pattern** (`uzex/adapters.py` lines 56–80):
```python
from pydantic import BaseModel, Field
from app.ingest.base import RawItemDraft, TestResult
from app.ingest.registry import register_adapter

class HtmlTableConfig(BaseModel):
    url: str = Field(..., description="Public URL of the HTML page containing the table")
    table_selector: str = Field(default="table", description="CSS selector for the target table")
    # ... other fields

class HtmlTableAdapter:
    type_name = "html_table"
    config_schema = HtmlTableConfig

    async def fetch(self, source) -> list[RawItemDraft]:
        ...

    async def test(self, config: dict) -> TestResult:
        ...
        # MUST cap sample_rows at 10 — TestResult.__post_init__ enforces this
        return TestResult(ok=True, sample_rows=rows[:10])

# Self-register at import time
register_adapter(HtmlTableAdapter())
```

**SSRF guard** — call `is_safe_url()` from `http_client.py` before any HTTP fetch (RESEARCH.md Security Domain):
```python
from app.ingest.http_client import fetch_url, is_safe_url

async def test(self, config: dict) -> TestResult:
    url = config["url"]
    if not is_safe_url(url):
        return TestResult(ok=False, error="URL is not publicly reachable (SSRF guard).")
    ...
```

**`telegram_channel` / `llm_page` adapters** — stub only. `test()` returns `TestResult(ok=False, error="Not available until Phase 5")`. `fetch()` returns `[]`. Config is saved normally; `is_enabled` stays `False` because `last_test_ok_at` is never set.

---

### Backend Test Files

#### `backend/tests/test_feed_api.py` + `test_dashboard_requests.py`

**Analog:** `backend/tests/test_webapp_requests_api.py` (exact)

**TestClient setup pattern** (`test_webapp_requests_api.py` lines 38–53):
```python
def _make_mock_client(id: int = 1) -> MagicMock:
    client = MagicMock()
    client.id = id
    return client

def _make_mock_request(id: int = 42, ...) -> MagicMock:
    from app.models.enums import RequestStatus
    req = MagicMock()
    req.id = id
    req.status = RequestStatus.new
    # ... set all fields required by the response schema
    return req
```

**Staff user + Bearer token pattern** (`test_rbac.py` lines 20–60 + `test_admin_source_types.py` lines 28–60):
```python
def _make_staff_user(role: str, user_id: int = 1) -> MagicMock:
    from app.models.enums import StaffRole
    user = MagicMock()
    user.id = user_id
    user.email = f"{role}@polymer.uz"
    user.role = StaffRole(role)
    user.is_active = True
    return user

def _auth_headers(user_id: int, role: str) -> dict[str, str]:
    from app.core.security import create_access_token
    token = create_access_token(subject=str(user_id), role=role)
    return {"Authorization": f"Bearer {token}"}

def _make_client_with_user(staff_user: MagicMock) -> TestClient:
    from app.core.db import get_db
    from app.main import create_app
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = staff_user
    def _override_get_db():
        yield mock_db
    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    return TestClient(application, raise_server_exceptions=True)
```

#### `backend/tests/test_source_wizard.py`

**Analog:** `backend/tests/test_admin_source_types.py` (exact — admin-only TestClient pattern)

Copy `_make_staff_user` / `_auth_headers` / `_make_client_with_user` helpers verbatim. Tests cover: `POST /sources/{id}/test` returns `{"ok": True, "sample_rows": [...]}` (≤10 rows), `PATCH /sources/{id}` with `is_enabled=true` and no test → 422, pending source save stays `is_enabled=false`.

---

### Frontend Files

#### `dashboard/app/(dashboard)/layout.tsx` (auth-guarded route group layout)

**Analog:** `dashboard/app/layout.tsx` (role-match)

**Root layout pattern** (`layout.tsx` lines 1–21) — `html.dark` is already set; the route-group layout wraps children in `QueryClientProvider` + sidebar shell:
```tsx
// Root layout already has:
<html lang="ru" className="dark">
  <body className="min-h-screen bg-background text-foreground antialiased">

// Route-group layout adds (no html/body — those are in root):
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  // auth redirect on 401 — check JWT from cookie/memory
  // render: <AppShell><Sidebar /><main>{children}</main></AppShell>
}
```

**Token usage pattern** (`layout.tsx` line 16 + `login/page.tsx` lines 25–64) — all colors via Tailwind token classes, no hex:
```tsx
// Correct:
className="bg-background-secondary border-border text-foreground-muted"
// Wrong (never do):
style={{ backgroundColor: '#1e293b' }}
```

#### `dashboard/app/login/page.tsx` (existing — extend in Phase 4)

**File exists** (`login/page.tsx` lines 1–72). Wire the stubbed `handleSubmit` to `POST /api/v1/auth/login` using the `lib/api.ts` fetch wrapper. The form structure, token classes, and `"use client"` directive are already correct — do not change them.

#### `dashboard/components/layout/Sidebar.tsx` + `AppShell.tsx`

**Analog:** `dashboard/app/login/page.tsx` (partial — token patterns only)

**Token class pattern** (`login/page.tsx` lines 25–64) — use these classes for sidebar surfaces:
```tsx
// Sidebar background:    bg-background-secondary
// Active item:           bg-background-tertiary border-l-2 border-accent text-foreground
// Hover state:           hover:bg-background-tertiary transition-colors duration-150
// Nav label (uppercase): text-xs font-semibold text-foreground-muted uppercase tracking-wider
// User footer:           border-t border-border
```

Focus ring (UI-SPEC Accessibility):
```tsx
className="focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
```

#### `dashboard/components/requests/RequestDetailPanel.tsx`

**Analog:** `dashboard/app/login/page.tsx` (partial — token patterns + form patterns)

**Form action button pattern** (`login/page.tsx` lines 62–66):
```tsx
// Primary CTA (Contact Buyer):
className="w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-white
           transition-colors hover:bg-accent-dark focus:outline-none
           focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background-secondary"

// Secondary / outline:
className="w-full rounded-md border border-border bg-transparent px-4 py-2 text-sm
           font-medium text-foreground hover:bg-background-tertiary ..."
```

Panel is a `shadcn Sheet` with `side="right"` and `role="dialog"` (UI-SPEC). Width fixed at 400px via inline style or a `w-[400px]` class.

Status badge mapping (UI-SPEC Color tokens):
```tsx
// Use token class names, never hex:
const STATUS_CLASSES = {
  new:         "text-status-new border-status-new",
  viewed:      "text-status-viewed border-status-viewed",
  in_progress: "text-status-in-progress border-status-in-progress",
  offer_sent:  "text-status-offer-sent border-status-offer-sent",
  matched:     "text-status-matched border-status-matched",
  closed:      "text-status-closed border-status-closed",
  cancelled:   "text-status-cancelled border-status-cancelled",
}
```

#### `dashboard/components/requests/AiAnalysisBlock.tsx`

**Analog:** `dashboard/app/login/page.tsx` (partial — token patterns only)

**D-01 / D-02 placeholder contract** (RESEARCH.md Pattern 8, lines 693–745):
```tsx
// Match Score: always render the bar, empty in Phase 4
<div style={{ width: ai?.match_score != null ? `${ai.match_score * 100}%` : '0%' }}
     className="h-full bg-accent transition-all" />

// Price Analysis: REAL data in Phase 4 (D-02) — no placeholder
{priceAnalysis ? (
  <span className={priceAnalysis.delta_pct > 0 ? 'text-accent' : 'text-urgency-medium'}>
    {priceAnalysis.label}
  </span>
) : null}

// Recommendation: honest placeholder
<p className="text-foreground-subtle italic text-sm">
  {ai?.recommendation ?? 'AI analysis available after Phase 5'}
</p>
```

#### `dashboard/components/prices/PriceChart.tsx`

**Analog:** `dashboard/app/login/page.tsx` (partial — token patterns only)

Recharts multi-series color mapping (UI-SPEC Color, chart lines section):
```tsx
// Use hex values ONLY inside Recharts stroke props (not className) — Recharts does not
// understand Tailwind. Map series to the same values declared in tailwind.config.ts:
const SERIES_COLORS = {
  pp_raffia: "#10b981",   // accent = emerald-500
  hdpe:      "#3b82f6",   // blue-500
  pet:       "#8b5cf6",   // violet-500
  pvc:       "#f59e0b",   // amber-500
}
// This is the ONLY exception to the no-hardcoded-hex rule — chart stroke props
// do not accept CSS variables. Comment this clearly in the file.
```

---

## Shared Patterns

### Authentication / RBAC Guard
**Source:** `backend/app/api/deps.py` lines 33–144
**Apply to:** All 7 new backend router files

```python
# All-staff read endpoints:
_: StaffUser = Depends(get_current_staff_user)

# Admin-only endpoints (sources, admin_users, alert_rules write):
_: StaffUser = Depends(require_admin)

# Role-scoped endpoints (request patch — analyst/trader/admin):
_: StaffUser = Depends(require_role(StaffRole.admin, StaffRole.analyst, StaffRole.trader))
```

`require_role` factory (`deps.py` lines 107–138) checks `current_user.role not in roles` and raises HTTP 403. The UI role-gating is UX-only; this is the security boundary.

### Audit Pattern
**Source:** `backend/app/services/audit_service.py` lines 23–60
**Apply to:** `dashboard_requests.py`, `alert_rules.py`, `sources.py` (enable/disable)

```python
from app.services.audit_service import write_audit

# Call BEFORE db.commit(). write_audit calls db.flush() internally.
write_audit(
    db=db,
    staff_user_id=current_user.id,   # NEVER from body (T-03-06)
    action="<entity>.<action>",       # e.g. "request.status_change"
    entity="<table_name>",
    entity_id=str(row.id),
    details={...},                    # optional JSONB context
)
db.commit()  # router owns the commit
```

### Service-Never-Commits Axiom
**Source:** `backend/app/services/request_service.py` lines 1–23 (module docstring)
**Apply to:** `alert_service.py` and any new service functions

All service functions: `db.flush()` to get generated IDs, never `db.commit()`. The router (or Celery task) owns `commit()`. This ensures audit rows are committed atomically with the action they trace.

### No-Hardcoded-Hex in Components
**Source:** `dashboard/app/login/page.tsx` throughout; `dashboard/app/layout.tsx` line 16
**Apply to:** All frontend component files

```tsx
// Correct — token class:
className="bg-background-secondary text-foreground-muted border-border"

// Exception — Recharts stroke/fill props only (Recharts ignores CSS vars):
stroke="#10b981"  // comment: matches tailwind.config.ts accent token
```

### Lazy Celery Task Import
**Source:** `backend/app/services/request_service.py` lines 207–209
**Apply to:** `alert_service.py`, any service that enqueues tasks

```python
# Import inside function body, not at module level:
from app.tasks.notify import send_delivery  # noqa: PLC0415
send_delivery.apply_async(args=[alert.id], queue="notify")
```

### `"use client"` Directive
**Source:** `dashboard/app/login/page.tsx` line 1
**Apply to:** All dashboard component and hook files that use `useState`, `useEffect`, `useQuery`, `EventSource`

Components under `app/(dashboard)/` that use browser APIs must start with `"use client"`. The layout itself can be a Server Component if it only wraps children.

---

## No Analog Found

Files with no close match in the codebase — planner should use RESEARCH.md Architecture Patterns section as the reference:

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `dashboard/hooks/useSSE.ts` | hook | streaming | No EventSource or SSE client code exists anywhere in the codebase. Use RESEARCH.md Pattern 2 (lines 328–404) as the implementation reference. |
| `dashboard/lib/api.ts` | utility | request-response | No frontend fetch wrapper exists. Standard pattern: `fetch` with `Authorization: Bearer ${token}` header + JSON parsing + 401 redirect to `/login`. |
| `dashboard/lib/queryClient.ts` | config | — | No TanStack Query client singleton exists yet. Standard: `new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } })` exported as singleton; wrap app in `<QueryClientProvider client={queryClient}>`. |
| `dashboard/lib/tz.ts` | utility | transform | No timezone utility exists. Use `Intl.DateTimeFormat` with `timeZone: 'Asia/Tashkent'` per RESEARCH.md "Don't Hand-Roll" table. |
| `dashboard/components/sources/JsonSchemaForm.tsx` | component | transform | No auto-form renderer exists. Use RESEARCH.md Pattern 4 (lines 504–566) including the Pydantic `anyOf` unwrapper for Optional fields (Pitfall 4). |
| `dashboard/app/(dashboard)/` route group | layout | — | Route groups (`(name)/`) are a Next.js App Router convention — no existing example in this repo. See RESEARCH.md Recommended Project Structure (lines 199–255). |
| Ingest adapters: `html_table`, `rss`, `telegram_channel`, `llm_page` | adapter | — | No `no_code=True` adapters exist yet. Closest analog is `uzex/adapters.py` for the structural pattern; the HTTP fetch + parse logic is net-new. |

---

## Metadata

**Analog search scope:** `backend/app/api/`, `backend/app/services/`, `backend/app/ingest/`, `backend/tests/`, `dashboard/app/`, `dashboard/components/` (where files exist)
**Files scanned:** 14 source files read directly
**Pattern extraction date:** 2026-06-17
