"""
/admin/settings + /admin/news — runtime switches, news-ops stats, and the news
approval queue for the internal dashboard.

The settings surface is read, write and reset, gated on the `appSettings` page —
plus `is_admin` for the two Didox credentials, whatever the page grant says.
Every write is validated by `Settings` itself and journalled to `audit_log`.

`.env` remains the contract and the default; this router writes only the
deliberate exceptions. What that buys, and the incident that shaped it, is in
`app/services/settings_service.py`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.domains.news import reports as report_service
from app.domains.news import service as news_service
from app.domains.signals import sources as source_service
from app.models.staff import StaffUser
from app.schemas.admin_settings import (
    NewsPromptCreate,
    NewsPromptOut,
    NewsPromptTry,
    NewsPromptTryOut,
    NewsStats,
    PendingNewsItem,
    PromptVersionItem,
    RunParserResult,
    SettingItem,
    SettingUpdate,
    SourceActivity,
)
from app.services import audit_service, prompt_service, settings_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-settings"])


# ── Runtime switches ───────────────────────────────────────────────────────────────


def _spec_or_404(key: str) -> settings_service.SettingSpec:
    spec = settings_service.SPECS.get(key)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown setting")
    return spec


def _assert_may_write(spec: settings_service.SettingSpec, user: StaffUser) -> None:
    """Refuse a write this staff member may not make.

    Two gates, not one. The page grant answers "may this person tune the
    platform", which is a reasonable thing to delegate. The `is_admin` check on
    a `sensitive` spec answers a different question — "may this person read and
    replace the Didox partner token" — and delegating the first should not
    silently delegate the second.
    """
    if not spec.overridable:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{spec.env_var} can only be changed in .env",
        )
    if spec.sensitive and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: administrator only",
        )


@router.get("/settings", response_model=list[SettingItem], summary="Show runtime switches")
def list_settings(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("appSettings", "read")),
) -> list[SettingItem]:
    """Every switch: what is running, what `.env` says, and who changed it.

    Resolved against the TABLE, not this process's cached snapshot — the
    snapshot may be a refresh behind, while the table is what a restart would
    load and what the other processes are converging on.
    """
    return [SettingItem.model_validate(s) for s in settings_service.get_all(db)]


# ── The news prompt ────────────────────────────────────────────────────────────
#
# Declared BEFORE the `/settings/{key}` routes below. FastAPI matches in
# declaration order, so a literal path that shares a prefix with a parameterised
# one has to come first or the parameter swallows it — the same ordering
# dependency `lab_orders/api_portal.py` documents.

_FAMILY = prompt_service.FAMILY_NEWS_EXTRACT


def _news_prompt_state(db: Session) -> NewsPromptOut:
    active = str(settings_service.get("news_prompt_version"))
    body = prompt_service.resolve_body(db, _FAMILY, active)
    if body is None:
        # The switch points at a version neither source has. Not reachable
        # through the panel (`allowed_values` is the union of both), but a stale
        # `.env` or a downgraded database can do it — and it is worth saying so
        # rather than rendering an empty editor that looks like an empty prompt.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active prompt version {active!r} exists in neither the image nor the database",
        )
    versions = prompt_service.list_versions(db, _FAMILY)
    return NewsPromptOut(
        active_version=active,
        body=body,
        shipped=next((v.shipped for v in versions if v.version == active), True),
        next_version=prompt_service.next_version(db, _FAMILY),
        max_chars=prompt_service.MAX_BODY_CHARS,
        versions=[
            PromptVersionItem(
                version=v.version,
                shipped=v.shipped,
                active=v.version == active,
                created_by=v.created_by,
                created_at=v.created_at,  # type: ignore[arg-type]
                note=v.note,
                size=v.size,
            )
            for v in versions
        ],
    )


@router.get(
    "/settings/news-prompt", response_model=NewsPromptOut, summary="The news prompt and its versions"
)
def get_news_prompt(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("appSettings", "read")),
) -> NewsPromptOut:
    """What the classifier is running, and every version it could run."""
    return _news_prompt_state(db)


@router.post(
    "/settings/news-prompt", response_model=NewsPromptOut, summary="Author a new prompt version"
)
def create_news_prompt(
    payload: NewsPromptCreate,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_page("appSettings", "write")),
) -> NewsPromptOut:
    """Save the edited text as a NEW version. Does not activate it.

    Saving and activating are two acts because they carry different risk: writing
    a version costs nothing and can be thrown away, while activating one changes
    how every article from that moment is classified. Splitting them is what lets
    an operator write a prompt, try it, and turn it on when they are ready to
    watch what it does.

    Re-saving unchanged text returns the version that already holds it rather
    than minting a near-identical neighbour.
    """
    try:
        prompt_service.create_version(
            db, _FAMILY, payload.body, note=payload.note, staff_user_id=user.id
        )
    except prompt_service.InvalidPrompt as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    # A new version changes what `allowed_values` offers, so every process needs
    # to see it before anyone can select it.
    settings_service.publish(db, set())
    return _news_prompt_state(db)


@router.post(
    "/settings/news-prompt/try",
    response_model=NewsPromptTryOut,
    summary="Try an unsaved prompt on one real article",
)
def try_news_prompt(
    payload: NewsPromptTry,
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("appSettings", "write")),
) -> NewsPromptTryOut:
    """Classify one already-collected article with the given text.

    The only check that exists for this prompt. The trade-signal extractor has a
    golden set and an eval gate; the news classifier has neither, so without this
    an operator's first sight of a new prompt's behaviour would be the articles it
    had already misclassified.

    A trial is not a run: no `parse_run` row, no signal, nothing persisted. A
    journal row for a prompt that was never active would be exactly the ambiguity
    the append-only version table exists to prevent.

    Gated on WRITE, not read — it spends real Anthropic tokens, and it settles
    them against the same daily budget as the pipeline. Leaking a reservation
    here would quietly shrink the budget for the work that matters.
    """
    from parsing.budget import (  # noqa: PLC0415
        check_and_reserve_tokens,
        record_actual_tokens,
        release_reservation,
    )
    from parsing.news_extractor import extract_news  # noqa: PLC0415
    from parsing.schemas import BudgetExceeded  # noqa: PLC0415 — budget re-exports it
    from parsing.text_prep import prepare_message_text  # noqa: PLC0415

    try:
        body = prompt_service._validated(payload.body)
    except prompt_service.InvalidPrompt as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    raw_item = news_service.sample_news_item(db, payload.raw_item_id)
    if raw_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No collected news item to try the prompt on",
        )
    prepared = prepare_message_text(raw_item.content or "")
    if not prepared:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That article has no text to classify"
        )

    estimate = 1200
    check_and_reserve_tokens(estimate)
    try:
        article, journal = extract_news(prepared, system_prompt=body)
    except BudgetExceeded:
        raise
    except Exception as exc:  # noqa: BLE001 — a failed trial must refund its reservation
        release_reservation(estimate)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"The trial failed: {exc}"[:400]
        ) from exc
    record_actual_tokens(
        estimate, int(journal.get("tokens_in", 0)) + int(journal.get("tokens_out", 0))
    )

    return NewsPromptTryOut(
        raw_item_id=raw_item.id,
        excerpt=prepared[:600],
        article=article.model_dump(mode="json"),
        tokens_in=int(journal.get("tokens_in", 0)),
        tokens_out=int(journal.get("tokens_out", 0)),
        latency_ms=float(journal.get("latency_ms", 0.0)),
    )


@router.put(
    "/settings/{key}", response_model=list[SettingItem], summary="Override one runtime switch"
)
def update_setting(
    key: str,
    payload: SettingUpdate,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_page("appSettings", "write")),
) -> list[SettingItem]:
    """Write an override for one switch, and return the whole list back.

    The full list rather than the one row, because a write can move a NEIGHBOUR:
    setting `gov_registry_mode` to `didox` is only accepted while a partner
    token exists, so the two rows are one state and showing half of it invites
    the operator to act on a stale picture.

    `write_audit` flushes without committing, so the override row and the audit
    row land in the same transaction — either both or neither.
    """
    spec = _spec_or_404(key)
    _assert_may_write(spec, user)

    before = settings_service.get(key)
    try:
        after = settings_service.set_override(db, key, payload.value, user.id)
    except settings_service.InvalidSetting as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    audit_service.write_audit(
        db,
        user.id,
        "settings.override",
        "app_settings",
        key,
        # A secret's value is never journalled. The audit trail's job is to say
        # who changed what and when; repeating the credential into a table with
        # a different retention story would undo the encryption two lines up.
        {"changed": True} if spec.sensitive else {"from": before, "to": after},
    )
    db.commit()
    settings_service.publish(db, {key})
    return [SettingItem.model_validate(s) for s in settings_service.get_all(db)]


@router.delete(
    "/settings/{key}", response_model=list[SettingItem], summary="Reset one switch to .env"
)
def reset_setting(
    key: str,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_page("appSettings", "write")),
) -> list[SettingItem]:
    """Delete the override, returning the switch to whatever `.env` says.

    The escape hatch that makes the rest of this screen safe to use: whatever an
    operator does here, the documented value is one click away.
    """
    spec = _spec_or_404(key)
    _assert_may_write(spec, user)

    before = settings_service.get(key)
    settings_service.clear_override(db, key)
    audit_service.write_audit(
        db,
        user.id,
        "settings.reset",
        "app_settings",
        key,
        {"changed": True} if spec.sensitive else {"from": before},
    )
    db.commit()
    settings_service.publish(db, {key})
    return [SettingItem.model_validate(s) for s in settings_service.get_all(db)]


# ── News-ops (dashboard admin panel) ───────────────────────────────────────────────

@router.get("/news/stats", response_model=NewsStats, summary="News-ops dashboard stats")
def news_stats(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("newsAdmin", "read")),
) -> NewsStats:
    ai_enabled = bool(settings_service.get("news_ai_enabled"))
    return NewsStats.model_validate(report_service.news_admin_stats(db, ai_enabled=ai_enabled))


@router.post("/news/run-parser", response_model=RunParserResult, summary="Trigger a news scan/parse now")
def run_parser(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("newsAdmin", "write")),
) -> RunParserResult:
    """Enqueue the RSS news fetch driver now (the 'Run Parser Now' button).

    Returns which sources the scan will hit so the UI can show it immediately; results
    stream into GET /admin/news/activity as the workers fetch + parse each source.
    """
    sources = source_service.enabled_rss_source_names(db)
    enqueued: list[str] = []
    try:
        from app.tasks.celery_app import celery_app  # noqa: PLC0415

        celery_app.send_task("rss_fetch", queue="ingest")
        enqueued.append("rss_fetch")
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin.run_parser.enqueue_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Could not enqueue the parser"
        ) from exc
    return RunParserResult(enqueued=enqueued, sources=sources, count=len(sources))


@router.get("/news/activity", response_model=list[SourceActivity], summary="Per-source scan activity")
def news_activity(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("newsAdmin", "read")),
) -> list[SourceActivity]:
    return [SourceActivity.model_validate(a) for a in source_service.news_source_activity(db)]


@router.get(
    "/news/pending", response_model=list[PendingNewsItem], summary="News awaiting approval"
)
def pending_news(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("newsAdmin", "read")),
) -> list[PendingNewsItem]:
    return [PendingNewsItem.model_validate(a) for a in news_service.list_pending_news(db)]


@router.post("/news/{signal_id}/approve", summary="Approve a pending news article")
def approve_news(
    signal_id: int,
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("newsAdmin", "write")),
) -> dict[str, object]:
    if not news_service.set_news_approval(db, signal_id, approved=True):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News article not found")
    db.commit()
    return {"id": signal_id, "approval": "approved"}


@router.post("/news/{signal_id}/reject", summary="Reject a pending news article")
def reject_news(
    signal_id: int,
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("newsAdmin", "write")),
) -> dict[str, object]:
    if not news_service.set_news_approval(db, signal_id, approved=False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News article not found")
    db.commit()
    return {"id": signal_id, "approval": "rejected"}
