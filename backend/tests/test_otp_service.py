"""Unit tests for otp_service (R1 W3 — T3.2).

Hermetic: FakeRedis + a mock DB session (the account upsert is asserted via mock
interactions — no real DB). Covers the W3 acceptance list: cooldown, daily caps
(phone + IP), attempt lockout, uniform wrong-code error, phone normalization, and
that the code never appears in logs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests._fake_redis import FakeRedis

_PHONE = "+998901234567"


def _mock_db_no_account() -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


# ── normalize_phone ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+998901234567", "+998901234567"),
        ("998901234567", "+998901234567"),
        ("901234567", "+998901234567"),
        ("+998 90 123 45 67", "+998901234567"),
        ("+998 (90) 123-45-67", "+998901234567"),
        ("00998901234567", "+998901234567"),
        ("+12025550123", "+12025550123"),
    ],
)
def test_normalize_phone_valid(raw: str, expected: str) -> None:
    from app.domains.accounts.otp import normalize_phone  # noqa: PLC0415

    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12345", "+", "++998", "9012"])
def test_normalize_phone_invalid(raw: str) -> None:
    from app.domains.accounts.otp import InvalidPhone, normalize_phone  # noqa: PLC0415

    with pytest.raises(InvalidPhone):
        normalize_phone(raw)


# ── request_code ──────────────────────────────────────────────────────────────


def test_request_code_stores_hash_resets_attempts_and_enqueues() -> None:
    from app.domains.accounts import otp as otp_service  # noqa: PLC0415

    fake = FakeRedis()
    fake.set(otp_service._attempts_key(_PHONE), "3")  # stale attempts must be cleared

    with (
        patch.object(otp_service, "_generate_code", return_value="123456"),
        patch.object(otp_service, "_enqueue_sms") as enqueue,
    ):
        result = otp_service.request_code(MagicMock(), fake, "901234567", "1.2.3.4")

    assert result is None
    assert fake.get(otp_service._code_key(_PHONE)) == otp_service._hash_code("123456")
    assert fake.get(otp_service._attempts_key(_PHONE)) is None
    enqueue.assert_called_once_with(_PHONE, "123456")


def test_request_code_cooldown_raises_rate_limited() -> None:
    from app.domains.accounts import otp as otp_service  # noqa: PLC0415

    fake = FakeRedis()
    with patch.object(otp_service, "_enqueue_sms"):
        otp_service.request_code(MagicMock(), fake, _PHONE, "1.2.3.4")
        with pytest.raises(otp_service.OtpRateLimited) as exc:
            otp_service.request_code(MagicMock(), fake, _PHONE, "1.2.3.4")

    assert exc.value.retry_after > 0


def test_request_code_daily_cap_per_phone() -> None:
    from app.domains.accounts import otp as otp_service  # noqa: PLC0415

    fake = FakeRedis()
    with patch.object(otp_service, "_enqueue_sms"):
        # OTP_MAX_SENDS_PER_DAY defaults to 5: calls 1..5 pass, the 6th trips the cap.
        for _ in range(5):
            fake.delete(otp_service._cooldown_key(_PHONE))  # simulate 60 s cooldown elapsing
            otp_service.request_code(MagicMock(), fake, _PHONE, "1.2.3.4")
        fake.delete(otp_service._cooldown_key(_PHONE))
        with pytest.raises(otp_service.OtpRateLimited):
            otp_service.request_code(MagicMock(), fake, _PHONE, "1.2.3.4")


def test_request_code_daily_cap_per_ip_across_phones() -> None:
    from app.domains.accounts import otp as otp_service  # noqa: PLC0415

    fake = FakeRedis()
    ip = "9.9.9.9"
    with patch.object(otp_service, "_enqueue_sms"):
        # Distinct phones (no per-phone cooldown/cap) but one IP → the IP cap trips.
        for i in range(5):
            otp_service.request_code(MagicMock(), fake, f"90000000{i}", ip)
        with pytest.raises(otp_service.OtpRateLimited):
            otp_service.request_code(MagicMock(), fake, "900000009", ip)


def test_request_code_never_logs_the_code(caplog) -> None:  # noqa: ANN001
    from app.domains.accounts import otp as otp_service  # noqa: PLC0415

    fake = FakeRedis()
    with (
        patch.object(otp_service, "_generate_code", return_value="654321"),
        patch.object(otp_service, "_enqueue_sms"),
        caplog.at_level("DEBUG"),
    ):
        otp_service.request_code(MagicMock(), fake, _PHONE, "1.2.3.4")

    assert "654321" not in caplog.text
    assert otp_service._hash_code("654321") not in caplog.text


# ── verify_code ───────────────────────────────────────────────────────────────


def test_verify_code_no_pending_code_is_invalid() -> None:
    from app.domains.accounts import otp as otp_service  # noqa: PLC0415

    fake = FakeRedis()
    with pytest.raises(otp_service.OtpInvalid):
        otp_service.verify_code(MagicMock(), fake, _PHONE, "123456")


def test_verify_code_wrong_code_is_invalid_and_counts_attempt() -> None:
    from app.domains.accounts import otp as otp_service  # noqa: PLC0415

    fake = FakeRedis()
    fake.setex(otp_service._code_key(_PHONE), 300, otp_service._hash_code("111111"))

    with pytest.raises(otp_service.OtpInvalid):
        otp_service.verify_code(MagicMock(), fake, _PHONE, "000000")

    assert fake.get(otp_service._attempts_key(_PHONE)) == "1"


def test_verify_code_locks_out_after_max_attempts() -> None:
    from app.domains.accounts import otp as otp_service  # noqa: PLC0415

    fake = FakeRedis()
    fake.setex(otp_service._code_key(_PHONE), 300, otp_service._hash_code("111111"))

    # OTP_MAX_VERIFY_ATTEMPTS defaults to 5: five wrong tries stay invalid, the 6th locks.
    for _ in range(5):
        with pytest.raises(otp_service.OtpInvalid):
            otp_service.verify_code(MagicMock(), fake, _PHONE, "000000")
    with pytest.raises(otp_service.OtpLocked):
        otp_service.verify_code(MagicMock(), fake, _PHONE, "000000")

    # Lockout invalidates the pending code so it can't be brute-forced further.
    assert fake.get(otp_service._code_key(_PHONE)) is None


def test_verify_code_success_creates_account() -> None:
    from app.domains.accounts import otp as otp_service  # noqa: PLC0415
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415

    fake = FakeRedis()
    fake.setex(otp_service._code_key(_PHONE), 300, otp_service._hash_code("123456"))
    db = _mock_db_no_account()

    account = otp_service.verify_code(db, fake, "901234567", "123456")

    assert isinstance(account, UserAccount)
    assert account.phone == _PHONE
    db.add.assert_called_once()
    db.flush.assert_called_once()
    # Successful verify consumes the code + attempt counter.
    assert fake.get(otp_service._code_key(_PHONE)) is None
    assert fake.get(otp_service._attempts_key(_PHONE)) is None


def test_verify_code_success_updates_existing_account() -> None:
    from app.domains.accounts import otp as otp_service  # noqa: PLC0415
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415

    fake = FakeRedis()
    fake.setex(otp_service._code_key(_PHONE), 300, otp_service._hash_code("123456"))
    existing = UserAccount(phone=_PHONE)
    existing.id = 5
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing

    account = otp_service.verify_code(db, fake, _PHONE, "123456")

    assert account is existing
    assert account.last_login_at is not None
    db.add.assert_not_called()
