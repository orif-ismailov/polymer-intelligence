"""
Runtime settings service (Phase 8d).

A thin, typed layer over the app_settings table. The admin panel edits a fixed set of
keys (declared in `_SPECS`); everything else falls back to a code default. Env config
(`settings`) stays the source of truth for secrets/infra — this only covers the handful
of operator toggles the news module exposes at runtime:

- news_ai_enabled       — run the LLM report digest (off ⇒ rule-based summaries only)
- news_require_approval — hold classified news until an analyst approves it
- report_auto_publish   — auto-publish generated reports (skip manual approve)
- llm_extract_model     — model the news extractor uses (defaults to LLM_EXTRACT_MODEL)
- news_prompt_version   — news extraction prompt version (defaults to the code version)

Service axiom (DEC-dep-owns-commit): flush only — the router/task owns the commit.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings as _config
from app.core.time import utcnow
from app.models.app_settings import AppSetting

# A setting value is a bool, string, or integer in the current spec set.
SettingValue = bool | str | int

# News extraction prompt version default — kept in sync with parsing.news_extractor
# (imported lazily to avoid building the Anthropic client at settings-import time).
_DEFAULT_NEWS_PROMPT_VERSION = "v2"


@dataclass(frozen=True)
class SettingSpec:
    key: str
    type: str  # "bool" | "str" | "int"
    default: SettingValue
    label: str
    min: int | None = None
    max: int | None = None


def _specs() -> tuple[SettingSpec, ...]:
    return (
        SettingSpec("news_ai_enabled", "bool", True, "AI summaries in reports"),
        SettingSpec("news_require_approval", "bool", False, "Require approval before news is published"),
        SettingSpec("report_auto_publish", "bool", False, "Auto-publish generated reports"),
        SettingSpec("llm_extract_model", "str", _config.LLM_EXTRACT_MODEL, "News AI model"),
        SettingSpec("news_prompt_version", "str", _DEFAULT_NEWS_PROMPT_VERSION, "News prompt version"),
        SettingSpec(
            "news_refresh_interval_minutes", "int", 60, "News refresh interval (minutes)",
            min=5, max=1440,
        ),
    )


_SPECS: dict[str, SettingSpec] = {s.key: s for s in _specs()}


def _coerce(spec: SettingSpec, value: object) -> SettingValue:
    """Validate/normalize an incoming value against its spec type."""
    if spec.type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if spec.type == "int":
        try:
            number = round(float(str(value).strip()))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{spec.key} must be an integer") from exc
        if spec.min is not None:
            number = max(number, spec.min)
        if spec.max is not None:
            number = min(number, spec.max)
        return number
    # str
    text = str(value).strip()
    if not text:
        raise ValueError(f"{spec.key} must be a non-empty string")
    return text


def _stored(db: Session) -> dict[str, object]:
    rows = db.execute(sa.select(AppSetting.key, AppSetting.value)).all()
    return {str(k): v for k, v in rows}


def get(db: Session, key: str) -> SettingValue:
    """Resolve one setting: stored override if present, else the code default."""
    spec = _SPECS.get(key)
    if spec is None:
        raise KeyError(key)
    row = db.get(AppSetting, key)
    if row is None:
        return spec.default
    return _coerce(spec, row.value)


def get_all(db: Session) -> list[dict[str, object]]:
    """Every known setting with its resolved value, default, and override flag."""
    stored = _stored(db)
    out: list[dict[str, object]] = []
    for spec in _SPECS.values():
        overridden = spec.key in stored
        value = _coerce(spec, stored[spec.key]) if overridden else spec.default
        out.append(
            {
                "key": spec.key,
                "type": spec.type,
                "label": spec.label,
                "value": value,
                "default": spec.default,
                "is_overridden": overridden,
            }
        )
    return out


def set_many(
    db: Session, updates: dict[str, object], staff_user_id: int | None
) -> list[dict[str, object]]:
    """Upsert a batch of overrides (validating each against its spec). Flush only.

    Raises KeyError for an unknown key and ValueError for a bad value — the router maps
    those to 400s so a typo can't silently no-op.
    """
    now = utcnow()
    for key, raw in updates.items():
        spec = _SPECS.get(key)
        if spec is None:
            raise KeyError(key)
        value = _coerce(spec, raw)
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value, updated_by=staff_user_id))
        else:
            row.value = value
            row.updated_by = staff_user_id
            row.updated_at = now
    db.flush()
    return get_all(db)
