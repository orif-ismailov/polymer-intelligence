# Phase 3: Client Circuit - Pattern Map

**Mapped:** 2026-06-16
**Files analyzed:** 28 (new/modified)
**Analogs found:** 26 / 28

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/api/webapp/requests.py` | router | request-response CRUD | `backend/app/api/auth.py` | role-match |
| `backend/app/api/webapp/me.py` | router | request-response CRUD | `backend/app/api/auth.py` | role-match |
| `backend/app/api/webapp/files.py` | router | file-I/O | `backend/app/api/admin_sources.py` | role-match |
| `backend/app/api/deps.py` | middleware/dep | request-response | `backend/app/api/deps.py` (extend) | exact |
| `backend/app/services/request_service.py` | service | CRUD + event-driven | `backend/app/services/signal_service.py` | role-match |
| `backend/app/services/storage_service.py` | service | file-I/O | `backend/app/services/raw_pipeline.py` | partial |
| `backend/app/schemas/webapp.py` | schema | transform | `backend/app/schemas/auth.py` | role-match |
| `backend/app/tasks/notify.py` (extend) | task | event-driven | `backend/app/tasks/notify.py` (exists) | exact |
| `backend/app/core/storage.py` | utility/config | file-I/O | `backend/app/core/config.py` | role-match |
| `backend/app/models/requests.py` | model | CRUD | itself (already exists, read-only) | exact |
| `telegram/__init__.py` | config | — | `backend/app/main.py` | partial |
| `telegram/bot.py` | provider | event-driven | `backend/app/main.py` (lifespan) | partial |
| `telegram/handlers/start.py` | controller | event-driven | `backend/app/api/auth.py` | partial |
| `telegram/templates/ru/start.txt` | config | — | no analog | no analog |
| `telegram/templates/uz/start.txt` | config | — | no analog | no analog |
| `telegram/templates/ru/status_change.txt` | config | — | no analog | no analog |
| `telegram/templates/uz/status_change.txt` | config | — | no analog | no analog |
| `webapp/src/main.tsx` | provider | — | `webapp/src/App.tsx` | role-match |
| `webapp/src/i18n/ru.json` | config | — | no full analog | partial |
| `webapp/src/i18n/uz.json` | config | — | no full analog | partial |
| `webapp/src/store/wizardStore.ts` | store | — | no analog | no analog |
| `webapp/src/api/client.ts` | utility | request-response | `backend/app/ingest/http_client.py` | partial |
| `webapp/src/pages/Home.tsx` | component | — | `webapp/src/App.tsx` | role-match |
| `webapp/src/pages/wizard/Step1.tsx` | component | request-response | `webapp/src/App.tsx` | role-match |
| `webapp/src/pages/wizard/Step2.tsx` | component | request-response | `webapp/src/App.tsx` | role-match |
| `webapp/src/pages/wizard/Step3.tsx` | component | file-I/O | `webapp/src/App.tsx` | role-match |
| `webapp/src/pages/wizard/Confirm.tsx` | component | — | `webapp/src/App.tsx` | role-match |
| `webapp/src/pages/MyRequests.tsx` | component | request-response | `webapp/src/App.tsx` | role-match |
| `webapp/src/pages/RequestDetail.tsx` | component | request-response | `webapp/src/App.tsx` | role-match |
| `webapp/src/pages/Settings.tsx` | component | request-response | `webapp/src/App.tsx` | role-match |
| `webapp/src/components/StepIndicator.tsx` | component | — | `webapp/src/App.tsx` | role-match |
| `webapp/src/components/StatusChip.tsx` | component | — | `webapp/src/App.tsx` | role-match |
| `webapp/src/components/FileUploader.tsx` | component | file-I/O | `webapp/src/App.tsx` | role-match |
| `webapp/src/components/RequestCard.tsx` | component | — | `webapp/src/App.tsx` | role-match |
| `webapp/src/components/StatusTimeline.tsx` | component | — | `webapp/src/App.tsx` | role-match |
| `deploy/docker-compose.dev.yml` | config | — | itself (extend) | exact |

---

## Pattern Assignments

### `backend/app/api/deps.py` — extend with `get_current_client` dep

**Analog:** `backend/app/api/deps.py` (lines 1-146)

**Existing auth pattern to extend** (lines 27-102):
```python
_bearer_scheme = HTTPBearer(auto_error=False)

def get_current_staff_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> StaffUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, ...)
    token = credentials.credentials
    try:
        payload = decode_token(token, expected_type="access")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, ...) from exc
    # identity from token, never body (T-03-06)
    subject = payload.get("sub")
    ...
    user = db.query(StaffUser).filter(StaffUser.id == staff_user_id).first()
    ...
    return user
```

**New dep to add** — mirror this pattern for `X-Telegram-Init-Data`:
```python
from fastapi import Header

def get_current_client(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
) -> Client:
    """Validate Telegram initData HMAC, upsert clients row, return Client.
    
    Dev-spec §3.2: header X-Telegram-Init-Data, HMAC per bot token, TTL 24h.
    T-03-06 equivalent: identity comes from verified initData, never request body.
    Never expose which field failed (generic 401).
    """
    if x_telegram_init_data is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    # verify_init_data() → raises 401 on bad sig or TTL expiry
    # ON CONFLICT (telegram_user_id) DO UPDATE language=EXCLUDED.language — idempotent
    ...
```

---

### `backend/app/api/webapp/requests.py` (router, CRUD request-response)

**Analog:** `backend/app/api/auth.py` (lines 33-84) and `backend/app/api/admin_sources.py` (lines 19-33)

**Router boilerplate pattern** (auth.py lines 16-33 / admin_sources.py lines 19-33):
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api.deps import get_current_client   # new dep for initData auth

router = APIRouter(prefix="/webapp", tags=["webapp"])
```

**CRUD handler pattern** (auth.py lines 38-84):
```python
@router.post("/requests", response_model=RequestOut, status_code=201)
def create_request(
    body: RequestCreate,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> RequestOut:
    """POST /webapp/requests — creates a purchase request.
    
    Identity comes from verified initData (client dep), never from body.
    Calls request_service.create_request() which generates REQ-YYYY-MM-DD-NNNNN,
    writes request_status_history row (new), enqueues notify task.
    """
    try:
        result = request_service.create_request(db=db, client=client, data=body)
        db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

**Audit write pattern** (auth.py lines 71-79, audit_service.py lines 51-59):
```python
from app.services.audit_service import write_audit

# Inside status-change handler (Phase 4 / internal PATCH /requests/{id}):
write_audit(
    db=db,
    staff_user_id=current_user.id,
    action="request.status_change",
    entity="requests",
    entity_id=str(request.id),
    details={"from_status": old_status.value, "to_status": new_status.value},
)
db.commit()  # caller commits — audit + action in one transaction
```

---

### `backend/app/services/request_service.py` (service, CRUD + event-driven)

**Analog:** `backend/app/services/signal_service.py` (lines 137-219) + `backend/app/services/audit_service.py` (lines 23-60)

**Service function signature pattern** (signal_service.py lines 137-160):
```python
def create_signal_from_parse(
    session: Session,
    raw_item: RawItem,
    parsed: Mapping[str, object],
) -> Signal:
    """Build Signal ORM. Added to session but NOT committed — caller commits."""
    ...
    signal = Signal(kind=kind, source_id=..., ...)
    logger.debug("signal_service.create_signal", extra={"kind": kind, ...})
    return signal
```

**Service pattern to replicate for request_service:**
```python
def create_request(db: Session, client: Client, data: RequestCreate) -> Request:
    """Generate REQ-YYYY-MM-DD-NNNNN, insert request + history row, enqueue notify.
    
    Does NOT commit — caller (router) commits.
    Number generation: per-date DB sequence via
      SELECT nextval('req_date_seq_{YYYYMMDD}') with CREATE SEQUENCE IF NOT EXISTS.
    """
    number = _generate_number(db)
    req = Request(number=number, client_id=client.id, status=RequestStatus.new, ...)
    db.add(req)
    db.flush()  # get req.id before history row
    
    hist = RequestStatusHistory(request_id=req.id, from_status=None,
                                 to_status=RequestStatus.new, changed_by=None)
    db.add(hist)
    db.flush()
    
    # Enqueue notify — after flush so req.id is known
    from app.tasks.notify import send_status_change_notification  # noqa: PLC0415
    send_status_change_notification.apply_async(
        args=[req.id], queue="notify"
    )
    
    logger.info("request_service.create", extra={"number": number, "client_id": client.id})
    return req

VALID_TRANSITIONS: dict[RequestStatus, set[RequestStatus]] = {
    RequestStatus.new: {RequestStatus.viewed},
    RequestStatus.viewed: {RequestStatus.in_progress},
    RequestStatus.in_progress: {RequestStatus.offer_sent, RequestStatus.matched,
                                  RequestStatus.closed, RequestStatus.cancelled},
    RequestStatus.offer_sent: {RequestStatus.matched, RequestStatus.closed,
                                RequestStatus.cancelled},
    RequestStatus.matched: {RequestStatus.closed},
    RequestStatus.closed: set(),
    RequestStatus.cancelled: set(),
}

def transition_status(db: Session, request: Request, to_status: RequestStatus,
                       changed_by: int | None = None) -> Request:
    """Validate + apply status transition; write history + audit; enqueue notify."""
    if to_status not in VALID_TRANSITIONS[request.status]:
        raise ValueError(f"Invalid transition {request.status} → {to_status}")
    old = request.status
    request.status = to_status
    db.add(RequestStatusHistory(request_id=request.id, from_status=old,
                                 to_status=to_status, changed_by=changed_by))
    db.flush()
    # audit_service.write_audit() here if changed_by is staff
    send_status_change_notification.apply_async(args=[request.id], queue="notify")
    return request
```

---

### `backend/app/tasks/notify.py` — extend with `send_status_change_notification`

**Analog:** `backend/app/tasks/notify.py` (existing, currently for source health) + `backend/app/tasks/ingest.py` (lines 1-64 task pattern)

**Celery task pattern** (ingest.py lines 32-64 / notify.py lines 32-63):
```python
from __future__ import annotations
import logging
from typing import Any
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(name="send_status_change_notification", queue="notify")
def send_status_change_notification(request_id: int) -> dict[str, Any]:
    """Send bot push to client on request status change. ≤30 s SLA (TZ §6.1.1).
    
    Loads request + client, reads client.language, renders template from
    telegram/templates/{lang}/status_change.txt, sends via aiogram Bot.send_message().
    Idempotent: if already sent (deliveries row exists), skip.
    """
    from sqlalchemy.orm import Session          # noqa: PLC0415
    from app.core.db import engine              # noqa: PLC0415
    
    logger.info("notify.status_change.start", extra={"request_id": request_id})
    try:
        with Session(engine) as session:
            # load, render, send, write deliveries row
            session.commit()
    except Exception as exc:
        logger.error("notify.status_change.error", extra={"error": str(exc), "request_id": request_id})
        return {"status": "error", "error": str(exc)}
    
    logger.info("notify.status_change.done", extra={"request_id": request_id})
    return {"status": "ok", "error": None}
```

Note: imports inside the task body (not at module level) — same pattern as `notify.py` lines 47-50 to avoid circular imports and keep module import-safe.

---

### `backend/app/core/storage.py` (S3/MinIO client, utility)

**Analog:** `backend/app/core/config.py` (lines 59-63) — S3 stubs already declared

**S3 settings already in config** (config.py lines 59-63):
```python
# ── S3 / MinIO file storage ───────────────────────────────────────────────
S3_ENDPOINT: str = ""
S3_ACCESS_KEY: str
S3_SECRET_KEY: str
S3_BUCKET: str = "polymer-files"
```

**Pattern to follow for storage.py** (mirroring config module-level singleton):
```python
"""MinIO/S3 client — first real use of S3_* config (Phase 3).

Use boto3 or aiobotocore. Construct once at module level; import `s3_client` everywhere.
"""
from __future__ import annotations
import boto3
from app.core.config import settings

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT or None,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
    )

s3_client = get_s3_client()
```

---

### `backend/app/services/storage_service.py` (service, file-I/O)

**Analog:** `backend/app/services/raw_pipeline.py` (save pattern with validation)

**Upload validation pattern to follow** (D-07, D-08):
```python
MAGIC_BYTES: dict[bytes, str] = {
    b"%PDF": "application/pdf",
    b"PK\x03\x04": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    b"\xff\xd8\xff": "image/jpeg",
}
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_FILES = 5

def validate_upload(content: bytes, filename: str) -> str:
    """Return detected MIME type or raise ValueError. Magic-byte check, not extension."""
    if len(content) > MAX_SIZE_BYTES:
        raise ValueError("file_too_large")
    for magic, mime in MAGIC_BYTES.items():
        if content.startswith(magic):
            return mime
    raise ValueError("invalid_file_type")

def upload_request_file(db: Session, request_id: int, content: bytes,
                         filename: str) -> RequestFile:
    """Validate + stream to MinIO, write request_files row. Does NOT commit."""
    mime = validate_upload(content, filename)
    storage_path = f"requests/{request_id}/{filename}"
    s3_client.put_object(Bucket=settings.S3_BUCKET, Key=storage_path, Body=content,
                          ContentType=mime)
    rf = RequestFile(request_id=request_id, file_name=filename, mime_type=mime,
                      size_bytes=len(content), storage_path=storage_path)
    db.add(rf)
    db.flush()
    return rf
```

---

### `backend/app/schemas/webapp.py` (Pydantic schemas)

**Analog:** `backend/app/schemas/auth.py`

**Schema pattern** (auth.py):
```python
from __future__ import annotations
from pydantic import BaseModel

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
```

**New schemas to create in same style:**
```python
from __future__ import annotations
import datetime, decimal
from pydantic import BaseModel, field_validator
from app.models.enums import RequestStatus, PriceBasis, Urgency

class RequestCreate(BaseModel):
    product_id: int
    grade_text: str | None = None
    volume: decimal.Decimal
    volume_unit: str = "MT"
    target_price: decimal.Decimal | None = None
    currency: str = "USD"
    incoterms: PriceBasis = PriceBasis.unknown
    destination_country: str = "UZ"
    port_or_city: str | None = None
    desired_date: datetime.date | None = None
    validity_days: int = 30
    urgency: Urgency = Urgency.medium
    comment: str | None = None

class RequestOut(BaseModel):
    id: int
    number: str
    status: RequestStatus
    created_at: datetime.datetime
    model_config = {"from_attributes": True}

class ClientProfilePatch(BaseModel):
    preferred_language: str | None = None  # 'ru' | 'uz'
```

---

### `telegram/bot.py` (aiogram 3 webhook, provider)

**Analog:** `backend/app/main.py` (lifespan pattern, lines 34-52) + FastAPI router include pattern (lines 103-105)

**Lifespan / startup pattern** (main.py lines 34-52):
```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.RUN_MIGRATIONS_ON_STARTUP:
        ...
    yield
```

**Bot wiring pattern for main.py lifespan extension:**
```python
# In telegram/bot.py
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp import SimpleRequestHandler  # or FastAPI integration
from app.core.config import settings

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()

# Include handlers
dp.include_router(start_router)

# In main.py lifespan, after yield-preamble:
# app.include_router(telegram_webhook_router, prefix="/telegram")
# Register webhook: await bot.set_webhook(url=..., secret_token=settings.WEBHOOK_SECRET)
```

**Router inclusion pattern** (main.py lines 103-106):
```python
application.include_router(telegram_webhook_router, prefix="")  # /telegram/webhook/{secret}
```

---

### `telegram/handlers/start.py` (aiogram handler, controller, event-driven)

**Analog:** `backend/app/api/auth.py` (handler structure, DB upsert + audit pattern)

**Handler pattern** (no business logic in handler — calls services):
```python
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.orm import Session
from app.core.db import engine
from app.models.requests import Client

start_router = Router()

@start_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """D-06: greeting RU/UZ + persistent Web App button + inline button.
    
    Upserts clients row (telegram_user_id, language from language_code).
    No business logic here — delegates to client_service.get_or_create_client().
    """
    lang = message.from_user.language_code or "ru"
    lang = lang if lang in ("ru", "uz") else "ru"
    
    with Session(engine) as db:
        client = client_service.get_or_create_client(
            db=db, telegram_user_id=message.from_user.id, language=lang
        )
        db.commit()
    
    # Load template from telegram/templates/{lang}/start.txt
    text = _load_template(lang, "start")
    await message.answer(text, reply_markup=_web_app_keyboard(lang))
```

---

### `webapp/src/main.tsx` (app entry, provider)

**Analog:** `webapp/src/App.tsx` (lines 1-89) — existing scaffold

**Current App.tsx pattern** (lines 1-10):
```tsx
// No hardcoded hex values — all colors via var(--tg-theme-*)
const styles = {
  app: {
    minHeight: "100vh",
    backgroundColor: "var(--tg-theme-bg-color, #1e293b)",
    color: "var(--tg-theme-text-color, #f8fafc)",
    fontFamily: "system-ui, sans-serif",
  },
  ...
}
```

**main.tsx provider wiring pattern:**
```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'  // or hash router for TG WebApp
import { I18nextProvider } from 'react-i18next'
import i18n from './i18n'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </I18nextProvider>
  </StrictMode>
)
```

---

### `webapp/src/store/wizardStore.ts` (zustand store, D-01)

**No analog in codebase.** Stack already includes `zustand@^4.5.4` (package.json line 23).

**Pattern from zustand docs + D-01 decision:**
```typescript
import { create } from 'zustand'

interface WizardState {
  step: 1 | 2 | 3
  // Step 1 fields (product + grade + volume — D-02 minimum required)
  product_id: number | null
  grade_text: string
  volume: string
  volume_unit: string
  // Step 2 fields (all optional)
  target_price: string
  incoterms: string
  destination_country: string
  port_or_city: string
  desired_date: string
  validity_days: number
  comment: string
  // Step 3 files
  files: File[]
  // Actions
  setField: <K extends keyof WizardState>(key: K, value: WizardState[K]) => void
  nextStep: () => void
  prevStep: () => void
  reset: () => void
}

export const useWizardStore = create<WizardState>((set) => ({
  step: 1,
  product_id: null,
  // ... initial values
  setField: (key, value) => set({ [key]: value }),
  nextStep: () => set((s) => ({ step: Math.min(3, s.step + 1) as 1|2|3 })),
  prevStep: () => set((s) => ({ step: Math.max(1, s.step - 1) as 1|2|3 })),
  reset: () => set({ step: 1, product_id: null, /* ... */ }),
}))
```

State is client-only — no persistence to server until submit (D-01).

---

### `webapp/src/api/client.ts` (API client utility, request-response)

**Analog:** `backend/app/ingest/http_client.py` (pattern: centralized client config) — closest available, partial.

**Pattern to follow for TG initData auth header:**
```typescript
const BASE_URL = "/api/v1"

function getInitData(): string {
  // @telegram-apps/sdk v2: import { retrieveLaunchParams } from '@telegram-apps/sdk'
  // retrieveLaunchParams().initDataRaw
  return window.Telegram?.WebApp?.initData ?? ""
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData(),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }))
    throw new ApiError(res.status, err.detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  createRequest: (body: RequestCreate) =>
    apiFetch<RequestOut>("/webapp/requests", { method: "POST", body: JSON.stringify(body) }),
  getRequests: () => apiFetch<RequestOut[]>("/webapp/requests"),
  getRequest: (id: number) => apiFetch<RequestOut>(`/webapp/requests/${id}`),
  uploadFile: (requestId: number, file: File) => { /* multipart */ },
  getMe: () => apiFetch<ClientProfile>("/webapp/me"),
  patchMe: (body: Partial<ClientProfile>) =>
    apiFetch<ClientProfile>("/webapp/me", { method: "PATCH", body: JSON.stringify(body) }),
}
```

---

### `webapp/src/pages/Home.tsx` and all page components (component, request-response)

**Analog:** `webapp/src/App.tsx` (entire file, lines 1-89)

**Color/style pattern** (App.tsx lines 1-61) — every page MUST follow:
```tsx
// Rule: NO hardcoded hex except #ef4444 (destructive, sole exception per 03-UI-SPEC.md)
const styles = {
  container: {
    minHeight: "100vh",
    backgroundColor: "var(--tg-theme-bg-color, #1e293b)",
    color: "var(--tg-theme-text-color, #f8fafc)",
    padding: "16px",   // md spacing token
  },
  card: {
    borderRadius: "12px",   // per UI-SPEC spacing note
    padding: "16px",
    backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
    marginBottom: "12px",   // card-gap constant
  },
  heading: {
    fontSize: "18px",    // screen heading / H1
    fontWeight: 600,
    color: "var(--tg-theme-text-color, #f8fafc)",
  },
  accentButton: {
    display: "block",
    width: "100%",
    minHeight: "44px",       // touch target WCAG 2.5.5
    padding: "12px 20px",
    borderRadius: "8px",
    backgroundColor: "var(--tg-theme-button-color, #10b981)",
    color: "var(--tg-theme-button-text-color, #ffffff)",
    border: "none",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
  },
} as const
```

**Typography scale** (from App.tsx, normalized):
- 18px/600 — screen heading (`headerTitle`)
- 15px/600 — card title, request number (`cardTitle`)
- 14px/400 — body text
- 13px/400 — hint/label/secondary (`cardText`, `headerSubtitle`)

**i18n usage pattern** (react-i18next, UI-SPEC key convention):
```tsx
import { useTranslation } from 'react-i18next'

export default function Home() {
  const { t } = useTranslation()
  return (
    <div style={styles.container}>
      <h1 style={styles.heading}>{t('home.heading')}</h1>
      <p style={{ fontSize: "13px", color: "var(--tg-theme-hint-color, #94a3b8)" }}>
        {t('home.subheading')}
      </p>
      <button style={styles.accentButton} type="button">
        {t('home.cta.submit')}
      </button>
    </div>
  )
}
```

---

### `webapp/src/pages/wizard/Step*.tsx` (wizard steps, react-hook-form + zod)

**Analog:** `webapp/src/App.tsx` (structure) + package.json confirms `react-hook-form@^7.52.1`, `zod@^3.23.8`, `@hookform/resolvers@^3.9.0`

**Form pattern** (D-03: per-step blocking validation):
```tsx
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

const step1Schema = z.object({
  product_id: z.number({ required_error: "required" }),
  volume: z.string().min(1).transform(Number),
  // grade_text optional (D-02)
})

type Step1Fields = z.infer<typeof step1Schema>

export default function Step1() {
  const { register, handleSubmit, formState: { errors } } = useForm<Step1Fields>({
    resolver: zodResolver(step1Schema),
  })
  // MainButton "Далее" disabled until valid — controlled via @telegram-apps/sdk
  
  return (
    <form>
      <label htmlFor="volume" style={{ fontSize: "13px", color: "var(--tg-theme-hint-color)" }}>
        {t('wizard.volume')}
      </label>
      <input
        id="volume"
        {...register("volume")}
        aria-describedby={errors.volume ? "volume-error" : undefined}
        style={{ backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)", ... }}
      />
      {errors.volume && (
        <span id="volume-error" style={{ fontSize: "13px", color: "#ef4444" }}>
          {errors.volume.message}
        </span>
      )}
    </form>
  )
}
```

Inline errors at 13px in `#ef4444` (sole permitted hardcoded hex, UI-SPEC §Color).

---

### `webapp/src/components/FileUploader.tsx` (component, file-I/O, D-08)

**Analog:** `webapp/src/App.tsx` (style pattern) — no file upload analog in codebase

**Client-side validation pattern** (D-08 limits enforced client-side AND backend):
```tsx
const ACCEPT_MIMES = ["application/pdf",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel", "image/jpeg"]
const MAX_SIZE = 10 * 1024 * 1024  // 10 MB
const MAX_FILES = 5

function validateFile(file: File): string | null {
  if (!ACCEPT_MIMES.includes(file.type)) return t('error.fileType')
  if (file.size > MAX_SIZE) return t('error.fileTooLarge')
  return null
}

// Remove button aria-label per UI-SPEC accessibility:
// aria-label={t('fileUploader.remove', { name: file.name })}
// haptic on remove: notificationOccurred('warning')
```

Files staged in local state until after `POST /webapp/requests` succeeds (D-01 sequencing).

---

### `webapp/src/components/StatusChip.tsx` (component)

**Color map from UI-SPEC §Color (status chip color map):**
```tsx
const STATUS_CHIP_STYLES: Record<string, { bg: string; color: string }> = {
  new:         { bg: "var(--tg-theme-button-color, #10b981)", color: "var(--tg-theme-button-color, #10b981)" },
  viewed:      { bg: "var(--tg-theme-hint-color, #94a3b8)",   color: "var(--tg-theme-hint-color, #94a3b8)" },
  in_progress: { bg: "var(--tg-theme-hint-color, #94a3b8)",   color: "var(--tg-theme-hint-color, #94a3b8)" },
  offer_sent:  { bg: "var(--tg-theme-link-color, #38bdf8)",   color: "var(--tg-theme-link-color, #38bdf8)" },
  matched:     { bg: "var(--tg-theme-button-color, #10b981)", color: "var(--tg-theme-button-color, #10b981)" },
  closed:      { bg: "var(--tg-theme-hint-color, #94a3b8)",   color: "var(--tg-theme-hint-color, #94a3b8)" },
  cancelled:   { bg: "#ef4444",                                color: "#ef4444" },
}
// bg used at 10-15% opacity on background; color at full opacity on text
// Status chip uses BOTH color AND text label (accessibility, UI-SPEC §Accessibility)
```

Client-facing label mapping (D-10) from `models/enums.py` `RequestStatus`:
```
new → Новая заявка
viewed|in_progress → На рассмотрении
offer_sent → Предложение получено
matched → Подобрано
closed → Закрыта
cancelled → Отменена
```

---

### `webapp/src/components/StatusTimeline.tsx` (component)

**Timezone pattern** (DEC-tz-handling, CONTEXT.md `<code_context>`):
- DB stores UTC (`created_at` on `request_status_history`)
- Display in Asia/Tashkent — use `Intl.DateTimeFormat` with `timeZone: "Asia/Tashkent"`

```tsx
function formatTashkent(utcStr: string): string {
  return new Intl.DateTimeFormat('ru', {
    timeZone: 'Asia/Tashkent',
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(utcStr))
}
```

---

## Shared Patterns

### initData HMAC Auth (backend)
**Source:** `backend/app/api/deps.py` (lines 27-102) — mirrored for new `get_current_client` dep
**Apply to:** All `/webapp/*` router endpoints
- Header: `X-Telegram-Init-Data`
- Verify HMAC against `settings.BOT_TOKEN` per Telegram docs
- TTL: 24 hours (reject `auth_date` older than 86400 s)
- On first login: upsert `clients` row with `language` from `language_code`
- Identity from verified payload, never request body (T-03-06 equivalent)
- Generic 401 on any failure (T-03-01 equivalent)

### Audit Write Pattern
**Source:** `backend/app/services/audit_service.py` (lines 23-60)
**Apply to:** `request_service.transition_status()` (when `changed_by` is staff)
```python
# db.flush() not db.commit() — caller commits audit + action together
write_audit(db=db, staff_user_id=changed_by, action="request.status_change",
            entity="requests", entity_id=str(request.id),
            details={"from": old.value, "to": to_status.value})
db.commit()
```

### Celery Task Pattern
**Source:** `backend/app/tasks/notify.py` (lines 27-63)
**Apply to:** `send_status_change_notification` task
- `@celery_app.task(name="...", queue="notify")`
- Lazy imports inside task body (avoid circular imports)
- `Session(engine)` context manager, `session.commit()` inside
- Return `{"status": "ok"|"error", "error": str|None}`
- Log `task_name.start`, `task_name.done`, `task_name.error`

### Tg-theme CSS Rule
**Source:** `webapp/src/App.tsx` (lines 1-61)
**Apply to:** Every component in `webapp/src/`
- Zero hardcoded hex values except `#ef4444` (destructive, sole exception)
- All colors: `var(--tg-theme-{property}, {fallback})`
- Touch targets: `min-height: 44px` on all interactive elements

### SQLAlchemy 2 Typed Model Pattern
**Source:** `backend/app/models/requests.py` (lines 40-210)
**Apply to:** Any future model additions
```python
from sqlalchemy.orm import Mapped, mapped_column
id: Mapped[int] = mapped_column(Integer, primary_key=True)
created_at: Mapped[datetime.datetime] = mapped_column(
    DateTime(timezone=True), nullable=False, server_default=func.now()
)
```
Always `DateTime(timezone=True)` — never naïve timestamps.

### Service Layer: No Commit in Service
**Source:** `backend/app/services/audit_service.py` (lines 56-60), `backend/app/services/signal_service.py` (line 209)
**Apply to:** All new service functions
```python
db.flush()  # flush to DB without committing — caller commits the full transaction
# do NOT call db.commit() in service layer
return orm_object
```

### Error Handling in Routers
**Source:** `backend/app/api/auth.py` (lines 59-65)
**Apply to:** All `/webapp/*` router handlers
```python
raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required",   # generic — never reveal which field failed
)
```
For validation errors from service layer: catch `ValueError`, re-raise as HTTP 422.

### Structlog Pattern
**Source:** `backend/app/services/signal_service.py` (lines 214-219)
**Apply to:** All new backend modules
```python
import logging
logger = logging.getLogger(__name__)
logger.info("service.action", extra={"key": value})
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `telegram/templates/ru/*.txt` | config | — | No template files exist yet; follow dev-spec §4.1 naming |
| `telegram/templates/uz/*.txt` | config | — | Same |
| `webapp/src/store/wizardStore.ts` | store | — | No zustand stores exist yet in codebase; follow zustand create() pattern from package docs |

---

## Metadata

**Analog search scope:** `backend/app/api/`, `backend/app/services/`, `backend/app/tasks/`, `backend/app/models/`, `backend/app/core/`, `webapp/src/`
**Files scanned:** 14 source files read in full
**Pattern extraction date:** 2026-06-16
