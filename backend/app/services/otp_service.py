"""Passwordless SMS-OTP auth for portal accounts (R1 W3 — T3.2).

`request_code` rate-limits (a 60 s resend cooldown + daily caps per phone AND per
IP), generates a 6-digit code, stores ONLY its sha256 in Redis under a short TTL,
and enqueues an SMS (fail-soft). It always returns None so a caller can't tell a
known phone from an unknown one. `verify_code` constant-time-checks the code with
an attempt lock, then upserts the `user_accounts` row and returns it.

The plaintext code is never logged and never persisted — only its sha256 lives in
Redis, and only for `OTP_TTL_SECONDS`. The single place a code is ever printed is
the console SMS driver (dev/CI).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

import redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.accounts import UserAccount
from app.models.enums import AccountStatus

logger = logging.getLogger(__name__)


# ── Domain exceptions (no `Error` suffix — house style, ruff N818 off) ────────


class InvalidPhone(Exception):
    """The supplied phone number is not a valid E.164 number."""


class OtpRateLimited(Exception):
    """Resend cooldown or daily cap hit. `retry_after` is seconds until retry."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("otp rate limited")
        self.retry_after = retry_after


class OtpInvalid(Exception):
    """No pending code, it expired, or the supplied code did not match."""


class OtpLocked(Exception):
    """Too many wrong attempts — the code was invalidated; request a new one."""


# ── Redis key helpers ─────────────────────────────────────────────────────────


def _cooldown_key(phone: str) -> str:
    return f"otp:cd:{phone}"


def _day_phone_key(phone: str) -> str:
    return f"otp:day:{phone}"


def _day_ip_key(ip: str) -> str:
    return f"otp:day:ip:{ip}"


def _code_key(phone: str) -> str:
    return f"otp:code:{phone}"


def _attempts_key(phone: str) -> str:
    return f"otp:att:{phone}"


def peek_key(phone: str) -> str:
    """Redis key holding the PLAINTEXT code — written only under the console driver in
    DEBUG (dev/CI), read by the double-gated /portal/auth/otp/peek e2e hook."""
    return f"otp:peek:{phone}"


# ── Phone normalization ───────────────────────────────────────────────────────


def normalize_phone(raw: str) -> str:
    """Normalize a phone number to E.164 (`+` + 8–15 digits).

    Uzbek national mobile numbers (9 digits) default to +998; a leading `+` (or
    `00`) international prefix is accepted as-is. Raises `InvalidPhone` on anything
    that isn't a plausible E.164 number.
    """
    cleaned = "".join(ch for ch in raw if ch not in " \t()-. ")
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]

    if cleaned.startswith("+"):
        digits = cleaned[1:]
    elif cleaned.startswith("998"):
        digits = cleaned
    elif len(cleaned) == 9 and cleaned.isdigit():
        digits = "998" + cleaned  # bare UZ national mobile
    else:
        digits = cleaned

    if not digits.isdigit() or not (8 <= len(digits) <= 15):
        raise InvalidPhone(f"not a valid phone number (got {len(digits)} digits)")
    return "+" + digits


# ── Internal helpers ──────────────────────────────────────────────────────────


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _seconds_until_utc_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))


def _ttl(redis_client: redis.Redis[str], key: str) -> int:
    """Positive seconds-to-expiry for `key`, or the cooldown as a safe fallback."""
    raw = redis_client.ttl(key)
    ttl = int(raw) if isinstance(raw, int) else 0
    return ttl if ttl > 0 else settings.OTP_RESEND_COOLDOWN_SECONDS


def _enforce_daily_cap(redis_client: redis.Redis[str], key: str) -> None:
    count = int(redis_client.incr(key))
    if count == 1:
        redis_client.expire(key, _seconds_until_utc_midnight(datetime.now(UTC)))
    if count > settings.OTP_MAX_SENDS_PER_DAY:
        raise OtpRateLimited(_ttl(redis_client, key))


def _render_otp_message(code: str) -> str:
    return f"Polymer Intelligence\nKod / Код: {code}"


def _enqueue_sms(phone: str, code: str) -> None:
    """Fire the send_sms notify task (fail-soft — a broker outage must not 500)."""
    try:
        from app.tasks.notify import send_sms  # noqa: PLC0415

        send_sms.apply_async(
            kwargs={"phone": phone, "text": _render_otp_message(code), "purpose": "otp"},
            queue="notify",
            retry=False,
        )
    except Exception as exc:  # noqa: BLE001 — never leak the code; never break the request
        logger.warning("otp.enqueue_failed", extra={"error": str(exc)})


def _upsert_account(db: Session, phone: str) -> UserAccount:
    """Return the account for `phone`, creating it (active) on first login."""
    now = datetime.now(UTC)
    account: UserAccount | None = (
        db.query(UserAccount).filter(UserAccount.phone == phone).first()
    )
    if account is None:
        account = UserAccount(phone=phone, status=AccountStatus.active, last_login_at=now)
        db.add(account)
        db.flush()  # assign id; caller commits
    else:
        account.last_login_at = now
    return account


# ── Public API ────────────────────────────────────────────────────────────────


def request_code(db: Session, redis_client: redis.Redis[str], phone: str, ip: str) -> None:
    """Rate-limited: issue a fresh OTP for `phone` and enqueue its SMS.

    Enforces (in order): resend cooldown, daily cap per phone, daily cap per IP.
    Always returns None so the response is uniform for known/unknown phones;
    over-limit raises `OtpRateLimited`. `db` is part of the port for symmetry with
    `verify_code` and future blocked-account gating; the R1 request path is
    DB-free.
    """
    normalized = normalize_phone(phone)

    # Resend cooldown (cheap SET NX EX). Present key ⇒ still cooling down.
    if not redis_client.set(
        _cooldown_key(normalized), "1", nx=True, ex=settings.OTP_RESEND_COOLDOWN_SECONDS
    ):
        raise OtpRateLimited(_ttl(redis_client, _cooldown_key(normalized)))

    # Daily caps (past-cooldown requests only, so ≤ OTP_MAX_SENDS_PER_DAY / day).
    _enforce_daily_cap(redis_client, _day_phone_key(normalized))
    _enforce_daily_cap(redis_client, _day_ip_key(ip))

    # Store sha256(code) (never the code) with TTL; reset the verify-attempt counter.
    code = _generate_code()
    redis_client.setex(_code_key(normalized), settings.OTP_TTL_SECONDS, _hash_code(code))
    redis_client.delete(_attempts_key(normalized))

    # Dev/CI ONLY (console driver + DEBUG): stash the plaintext so the e2e peek hook
    # can read the code without SMS. Never written in prod (eskiz or DEBUG off).
    if settings.DEBUG and settings.SMS_PROVIDER == "console":
        redis_client.setex(peek_key(normalized), settings.OTP_TTL_SECONDS, code)

    _enqueue_sms(normalized, code)


def verify_code(db: Session, redis_client: redis.Redis[str], phone: str, code: str) -> UserAccount:
    """Verify `code` for `phone`; on success upsert + return the `UserAccount`.

    Raises `OtpInvalid` when there's no pending code, it expired, or the code is
    wrong; `OtpLocked` after `OTP_MAX_VERIFY_ATTEMPTS` wrong tries (the pending
    code is invalidated). The caller commits the returned account's transaction.
    """
    normalized = normalize_phone(phone)

    stored = redis_client.get(_code_key(normalized))
    if stored is None:
        raise OtpInvalid("no pending code")

    attempts = int(redis_client.incr(_attempts_key(normalized)))
    if attempts == 1:
        redis_client.expire(_attempts_key(normalized), settings.OTP_TTL_SECONDS)
    if attempts > settings.OTP_MAX_VERIFY_ATTEMPTS:
        redis_client.delete(_code_key(normalized), _attempts_key(normalized))
        raise OtpLocked("too many attempts")

    stored_hash = stored.decode() if isinstance(stored, bytes) else str(stored)
    if not hmac.compare_digest(stored_hash, _hash_code(code)):
        raise OtpInvalid("wrong code")

    redis_client.delete(_code_key(normalized), _attempts_key(normalized))
    return _upsert_account(db, normalized)
