"""Fixed dev OTP code (`OTP_DEV_CODE`) — dev convenience that must never reach prod.

Typing a known code beats reading it out of a log on every demo login, but a
predictable OTP is an authentication bypass: anyone who knows a phone number can
sign in as its owner. So the feature is gated three times over, and these tests
exist to keep all three gates honest:

  1. **Off by default.** An unset `OTP_DEV_CODE` changes nothing — the code stays
     random. Nobody gets a fixed OTP by upgrading.
  2. **The same double gate as the peek hook** at the point of use: honoured only
     when `DEBUG` *and* `SMS_PROVIDER=console`. Either one off ⇒ random again, so
     a leftover `.env` line cannot weaken a stack that sends real SMS.
  3. **Fail-fast at startup** on the one combination that is unambiguous operator
     error: a fixed code configured while a real SMS provider is selected. There
     the gate above would silently ignore the setting, and silence is the wrong
     answer — the operator asked for something dangerous and should be told.

What is deliberately NOT changed: verification. `verify_code` still compares
against `sha256(code)` in Redis, so a fixed code is checked by exactly the same
path as a random one, and the wrong-code / lockout behaviour is untouched.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests._fake_redis import FakeRedis

_PHONE = "+998901234567"
_ZEROS = "000000"


def _dev_settings(code: str = _ZEROS):  # noqa: ANN202
    """Patch settings into "development": fixed code + DEBUG + console SMS."""
    from app.core.config import settings  # noqa: PLC0415

    return (
        patch.object(settings, "OTP_DEV_CODE", code),
        patch.object(settings, "DEBUG", True),
        patch.object(settings, "SMS_PROVIDER", "console"),
    )


# ── gate 1: off by default ────────────────────────────────────────────────────


def test_the_setting_ships_empty_so_nothing_changes_by_default() -> None:
    """The shipped default must leave the OTP random — no opt-out required."""
    from app.core.config import Settings  # noqa: PLC0415

    assert Settings.model_fields["OTP_DEV_CODE"].default == ""


def test_an_empty_setting_leaves_the_code_random() -> None:
    from app.core.config import settings  # noqa: PLC0415
    from app.services import otp_service  # noqa: PLC0415

    with (
        patch.object(settings, "OTP_DEV_CODE", ""),
        patch.object(settings, "DEBUG", True),
        patch.object(settings, "SMS_PROVIDER", "console"),
    ):
        codes = {otp_service._generate_code() for _ in range(40)}

    assert len(codes) > 1, "an unset OTP_DEV_CODE must not fix the code"
    assert all(c.isdigit() and len(c) == otp_service.CODE_LENGTH for c in codes)


# ── gate 2: the double gate at the point of use ───────────────────────────────


def test_a_configured_code_is_used_in_development() -> None:
    from app.services import otp_service  # noqa: PLC0415

    fixed, debug, provider = _dev_settings()
    with fixed, debug, provider:
        assert {otp_service._generate_code() for _ in range(10)} == {_ZEROS}


def test_a_configured_code_is_ignored_when_debug_is_off() -> None:
    """Staging with DEBUG off must not hand out a guessable OTP."""
    from app.core.config import settings  # noqa: PLC0415
    from app.services import otp_service  # noqa: PLC0415

    with (
        patch.object(settings, "OTP_DEV_CODE", _ZEROS),
        patch.object(settings, "DEBUG", False),
        patch.object(settings, "SMS_PROVIDER", "console"),
    ):
        codes = {otp_service._generate_code() for _ in range(40)}

    assert codes != {_ZEROS}


def test_a_configured_code_is_ignored_when_real_sms_is_selected() -> None:
    """The second half of the gate: a real SMS provider always wins.

    The startup validator refuses this combination outright, so reaching here
    means someone patched settings at runtime — the defence still has to hold.
    """
    from app.core.config import settings  # noqa: PLC0415
    from app.services import otp_service  # noqa: PLC0415

    with (
        patch.object(settings, "OTP_DEV_CODE", _ZEROS),
        patch.object(settings, "DEBUG", True),
        patch.object(settings, "SMS_PROVIDER", "eskiz"),
    ):
        codes = {otp_service._generate_code() for _ in range(40)}

    assert codes != {_ZEROS}


# ── the whole request path, not just the generator ────────────────────────────


def test_request_code_stores_the_hash_of_the_fixed_code() -> None:
    """End to end through `request_code`: the fixed code is what gets verified."""
    from app.services import otp_service  # noqa: PLC0415

    fake = FakeRedis()
    fixed, debug, provider = _dev_settings()
    with fixed, debug, provider, patch.object(otp_service, "_enqueue_sms") as enqueue:
        otp_service.request_code(MagicMock(), fake, _PHONE, "1.2.3.4")

    assert fake.get(otp_service._code_key(_PHONE)) == otp_service._hash_code(_ZEROS)
    assert fake.get(otp_service.peek_key(_PHONE)) == _ZEROS
    enqueue.assert_called_once_with(_PHONE, _ZEROS)


def test_the_fixed_code_verifies_through_the_normal_path() -> None:
    """No shortcut in `verify_code` — it is the same sha256 comparison."""
    from app.services import otp_service  # noqa: PLC0415

    fake = FakeRedis()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    fixed, debug, provider = _dev_settings()
    with fixed, debug, provider, patch.object(otp_service, "_enqueue_sms"):
        otp_service.request_code(db, fake, _PHONE, "1.2.3.4")
        otp_service.verify_code(db, fake, _PHONE, _ZEROS)

    assert fake.get(otp_service._code_key(_PHONE)) is None, "consumed on success"


def test_a_wrong_code_is_still_refused_with_a_fixed_code_configured() -> None:
    """Fixing the code must not turn `verify_code` into a no-op."""
    from app.services import otp_service  # noqa: PLC0415

    fake = FakeRedis()
    fixed, debug, provider = _dev_settings()
    with fixed, debug, provider, patch.object(otp_service, "_enqueue_sms"):
        otp_service.request_code(MagicMock(), fake, _PHONE, "1.2.3.4")
        with pytest.raises(otp_service.OtpInvalid):
            otp_service.verify_code(MagicMock(), fake, _PHONE, "111111")


# ── gate 3: startup validation ────────────────────────────────────────────────


def _settings_with(monkeypatch, **env: str):  # noqa: ANN001, ANN202
    """Build a fresh Settings from the test env plus overrides."""
    from app.core.config import Settings  # noqa: PLC0415
    from tests.conftest import _TEST_ENV  # noqa: PLC0415

    for key, value in {**_TEST_ENV, **env}.items():
        monkeypatch.setenv(key, value)
    return Settings()  # type: ignore[call-arg]


def test_a_fixed_code_with_a_real_sms_provider_fails_at_startup(monkeypatch) -> None:  # noqa: ANN001
    """The dangerous combination is refused loudly, not ignored quietly."""
    with pytest.raises(ValueError, match="OTP_DEV_CODE"):
        _settings_with(
            monkeypatch,
            OTP_DEV_CODE=_ZEROS,
            SMS_PROVIDER="eskiz",
            ESKIZ_EMAIL="x@example.com",
            ESKIZ_PASSWORD="secret",
        )


@pytest.mark.parametrize("bad", ["12345", "1234567", "00000a", "abcdef", "0000 0"])
def test_a_code_that_is_not_six_digits_fails_at_startup(monkeypatch, bad: str) -> None:  # noqa: ANN001
    """A 5-digit "dev code" would never match, and the failure would look like a
    broken OTP rather than a typo in .env."""
    with pytest.raises(ValueError, match="OTP_DEV_CODE"):
        _settings_with(monkeypatch, OTP_DEV_CODE=bad)


def test_zeros_are_accepted(monkeypatch) -> None:  # noqa: ANN001
    settings = _settings_with(monkeypatch, OTP_DEV_CODE=_ZEROS)
    assert settings.OTP_DEV_CODE == _ZEROS


def test_the_console_default_accepts_a_fixed_code(monkeypatch) -> None:  # noqa: ANN001
    settings = _settings_with(monkeypatch, OTP_DEV_CODE=_ZEROS, SMS_PROVIDER="console")
    assert settings.OTP_DEV_CODE == _ZEROS


def test_the_validated_length_matches_the_generator(monkeypatch) -> None:  # noqa: ANN001
    """config.py validates a literal length; otp_service owns the real one.

    Two numbers that must agree, in two modules that cannot import each other —
    so something has to assert it.
    """
    from app.services.otp_service import CODE_LENGTH  # noqa: PLC0415

    settings = _settings_with(monkeypatch, OTP_DEV_CODE="0" * CODE_LENGTH)
    assert len(settings.OTP_DEV_CODE) == CODE_LENGTH


# ── the code still never reaches a log by itself ──────────────────────────────


def test_the_fixed_code_is_not_logged_by_otp_service(caplog) -> None:  # noqa: ANN001
    """`otp_service` never logs a code, fixed or not — only the console SMS driver
    does, and only under its own gate."""
    from app.services import otp_service  # noqa: PLC0415

    fake = FakeRedis()
    fixed, debug, provider = _dev_settings()
    with (
        fixed,
        debug,
        provider,
        patch.object(otp_service, "_enqueue_sms"),
        caplog.at_level("DEBUG"),
    ):
        otp_service.request_code(MagicMock(), fake, _PHONE, "1.2.3.4")

    assert _ZEROS not in caplog.text


def test_non_positive_otp_windows_are_refused_at_startup() -> None:
    """A "no cooldown" of 0 must not be accepted.

    `otp_service.request_code` passes these to Redis as `SET … EX`, which refuses
    a non-positive TTL — so a 0 here is not "disabled", it is a 500 on every
    sign-in with nothing in the symptom pointing at `.env`. Reaching for 0 is the
    obvious way to write "off", which is exactly why it has to fail loudly.
    """
    import pydantic  # noqa: PLC0415

    from app.core.config import Settings  # noqa: PLC0415

    for field in ("OTP_RESEND_COOLDOWN_SECONDS", "OTP_TTL_SECONDS"):
        for bad in (0, -1):
            with pytest.raises(pydantic.ValidationError):
                Settings(**{field: bad})  # type: ignore[arg-type]

    # And the documented defaults still load.
    assert Settings().OTP_RESEND_COOLDOWN_SECONDS >= 1
