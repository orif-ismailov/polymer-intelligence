"""
Telegram Web App client service — initData HMAC verification and client upsert.

Dev-spec §3.2: Telegram WebApp initData HMAC algorithm:
  secret_key = HMAC_SHA256(key=b"WebAppData", msg=BOT_TOKEN)
  check       = HMAC_SHA256(key=secret_key, msg=data_check_string)
  data_check_string = sorted key=value pairs (excluding 'hash') joined by '\\n'

T-03-01: HMAC comparison uses hmac.compare_digest to prevent timing attacks.
T-03-02: auth_date TTL enforced (TELEGRAM_INIT_DATA_TTL_SECONDS, default 86400 s).
T-03-03: Every failure path raises the same InvalidInitData (ValueError subclass),
         so callers return a generic 401 without revealing which check failed.
T-03-06: identity always derived from the verified initData payload, never from
         the request body.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.parse

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.requests import Client

logger = logging.getLogger(__name__)

# Module-level constant sourced from settings so tests can patch settings in conftest.
INIT_DATA_TTL_SECONDS: int = settings.TELEGRAM_INIT_DATA_TTL_SECONDS


class InvalidInitData(ValueError):
    """Raised by verify_init_data on any HMAC, TTL, or parse failure.

    Always a ValueError subclass so callers can catch ValueError to return a
    generic 401 without exposing which check failed (T-03-03).
    """


def verify_init_data(raw: str) -> dict[str, object]:
    """Verify Telegram Web App initData and return the parsed dict.

    Implements the Telegram WebApp data-check algorithm exactly:
      1. URL-decode the query string.
      2. Extract the 'hash' field.
      3. Build data_check_string: sort remaining fields alphabetically,
         join as 'key=value' pairs separated by '\\n'.
      4. Derive secret_key = HMAC_SHA256(key=b"WebAppData", msg=BOT_TOKEN).
      5. Derive check hash = HMAC_SHA256(key=secret_key, msg=data_check_string).
      6. Compare with hmac.compare_digest (T-03-01: constant-time comparison).
      7. Parse auth_date and verify it is within TTL (T-03-02).
      8. JSON-parse the 'user' field.

    Args:
        raw: The raw URL-encoded initData string from the X-Telegram-Init-Data header.

    Returns:
        The parsed dict with all fields including a parsed 'user' sub-dict.

    Raises:
        InvalidInitData: On any verification failure (wrong hash, expired TTL,
            malformed input, missing fields). Always a ValueError subclass so
            callers return a generic 401 (T-03-03).
    """
    if not raw or not raw.strip():
        raise InvalidInitData("empty initData")

    try:
        fields = dict(urllib.parse.parse_qsl(raw, keep_blank_values=True))
    except Exception as exc:
        raise InvalidInitData("malformed initData query string") from exc

    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise InvalidInitData("missing hash field")

    # Build data_check_string: sorted key=value pairs (hash excluded), joined by \n
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(fields.items())
    )

    # Derive secret_key from bot token
    secret_key = hmac.new(
        b"WebAppData",
        settings.BOT_TOKEN.encode(),
        hashlib.sha256,
    ).digest()

    # Derive expected hash
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison (T-03-01)
    if not hmac.compare_digest(expected_hash, received_hash):
        raise InvalidInitData("HMAC mismatch")

    # TTL check (T-03-02)
    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidInitData("missing or invalid auth_date") from exc

    age_seconds = int(time.time()) - auth_date
    if age_seconds > INIT_DATA_TTL_SECONDS:
        raise InvalidInitData(f"initData expired: age={age_seconds}s > TTL={INIT_DATA_TTL_SECONDS}s")

    # Parse the 'user' JSON field
    try:
        user_raw = fields.get("user", "{}")
        fields["user"] = json.loads(user_raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidInitData("malformed user field") from exc

    fields["auth_date"] = auth_date  # overwrite with int for convenience
    return fields


def get_or_create_client(
    db: Session,
    telegram_user_id: int,
    language: str,
    contact_name: str | None = None,
) -> Client:
    """Idempotently upsert a clients row keyed on telegram_user_id.

    Maps language_code to 'ru' or 'uz'; any other value defaults to 'ru'.
    Does NOT commit — caller commits the full transaction (Service Layer pattern:
    db.flush() only, never db.commit()).

    Args:
        db: The active SQLAlchemy session.
        telegram_user_id: The Telegram user's integer ID from verified initData.
        language: The Telegram language_code from the verified initData.
        contact_name: Optional display name for the client.

    Returns:
        The existing or newly created Client ORM object.
    """
    # Normalize language_code → 'ru' | 'uz' only; everything else defaults to 'ru'
    normalized_language = language if language in ("ru", "uz") else "ru"

    existing: Client | None = (
        db.query(Client)
        .filter(Client.telegram_user_id == telegram_user_id)
        .first()
    )
    if existing is not None:
        logger.debug(
            "client_service.get_or_create_client.existing",
            extra={"telegram_user_id": telegram_user_id},
        )
        return existing

    new_client = Client(
        telegram_user_id=telegram_user_id,
        language=normalized_language,
        contact_name=contact_name,
    )
    db.add(new_client)
    db.flush()  # get new_client.id; do NOT commit — caller commits

    # Re-fetch so the caller gets a fully-populated ORM object
    created: Client | None = (
        db.query(Client)
        .filter(Client.telegram_user_id == telegram_user_id)
        .first()
    )
    if created is None:
        # Should never happen after a successful flush, but fail loudly if it does
        raise RuntimeError(
            f"get_or_create_client: failed to fetch newly inserted client "
            f"(telegram_user_id={telegram_user_id})"
        )

    logger.info(
        "client_service.get_or_create_client.created",
        extra={"telegram_user_id": telegram_user_id, "language": normalized_language},
    )
    return created
