"""Portal auth API tests (R1 W3 — T3.3 acceptance).

TestClient with get_db (mock session) + get_redis (FakeRedis) overridden. Where a
test needs a persisted account with a real id, verify_code is patched to return a
canned UserAccount (the service's own logic is unit-tested in test_otp_service).

Covers the W3 acceptance list: cooldown 429, wrong-code uniform error, success
issues a working token + cookie, JWT audience isolation both directions, blocked
account 403, refresh rotation, send_sms enqueue, and code-absent-from-logs.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis

_REQUEST = "/api/v1/portal/auth/otp/request"
_VERIFY = "/api/v1/portal/auth/otp/verify"
_REFRESH = "/api/v1/portal/auth/refresh"
_LOGOUT = "/api/v1/portal/auth/logout"
_ME = "/api/v1/portal/me"
_PHONE = "+998901234567"


@pytest.fixture
def portal_app() -> Iterator[tuple[TestClient, FakeRedis, MagicMock]]:
    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    app = create_app()
    fake = FakeRedis()
    db = MagicMock()

    def _override_db() -> Iterator[MagicMock]:
        yield db

    def _override_redis() -> Iterator[FakeRedis]:
        yield fake

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, fake, db


def _account(account_id: int, status: str = "active"):  # noqa: ANN202
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    acct = UserAccount(phone=_PHONE, language="ru", status=AccountStatus(status))
    acct.id = account_id
    return acct


# ── OTP request ───────────────────────────────────────────────────────────────


def test_otp_request_returns_204(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    with patch("app.domains.accounts.otp._enqueue_sms"):
        resp = client.post(_REQUEST, json={"phone": _PHONE})
    assert resp.status_code == 204


def test_otp_request_second_call_is_rate_limited_with_retry_after(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    with patch("app.domains.accounts.otp._enqueue_sms"):
        client.post(_REQUEST, json={"phone": _PHONE})
        resp = client.post(_REQUEST, json={"phone": _PHONE})
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0


def test_otp_request_invalid_phone_returns_422(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    with patch("app.domains.accounts.otp._enqueue_sms"):
        resp = client.post(_REQUEST, json={"phone": "not-a-phone"})
    assert resp.status_code == 422


def test_otp_request_enqueues_send_sms_without_logging_the_code(portal_app, caplog) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    with (
        patch("app.domains.accounts.otp._generate_code", return_value="654321"),
        patch("app.tasks.notify.send_sms.apply_async") as apply_async,
        caplog.at_level("DEBUG"),
    ):
        resp = client.post(_REQUEST, json={"phone": _PHONE})

    assert resp.status_code == 204
    apply_async.assert_called_once()
    enqueued = apply_async.call_args.kwargs["kwargs"]
    assert enqueued["phone"] == _PHONE
    assert enqueued["purpose"] == "otp"
    assert "654321" in enqueued["text"]  # the code rides in the SMS body …
    assert "654321" not in caplog.text  # … but is never logged


# ── Per-IP cap: which header identifies the caller ────────────────────────────
# The cap is only worth as much as the header it keys on. nginx APPENDS to
# X-Forwarded-For (`$proxy_add_x_forwarded_for`) and OVERWRITES X-Real-IP
# (`proxy_set_header`), so only the latter is caller-proof. These two tests pin
# that: one proves a forged header buys nothing, the other proves the trusted
# header still separates real callers (so the fix isn't "ignore all headers").
#
# Distinct phones throughout — the per-phone cooldown would otherwise 429 first
# and both tests would pass without ever reaching the per-IP bucket.

_CAP = 5  # settings.OTP_MAX_SENDS_PER_DAY, pinned in tests/conftest.py


def _request_from(client, phone: str, headers: dict[str, str]):  # noqa: ANN001, ANN202
    with patch("app.domains.accounts.otp._enqueue_sms"):
        return client.post(_REQUEST, json={"phone": phone}, headers=headers)


def test_forged_x_forwarded_for_cannot_escape_the_per_ip_cap(portal_app) -> None:  # noqa: ANN001
    """A caller rotating X-Forwarded-For stays in one bucket.

    Regression test for the spoofable-IP bug: `_client_ip` used to return
    `xff.split(",")[0]`, which is the value the CALLER sent (nginx appends its
    own after it). Every forged value therefore minted a fresh bucket and the
    cap never fired — unlimited OTP breadth across phone numbers on a metered
    SMS account. Each request below carries a different forged XFF; the cap must
    still fire on schedule.
    """
    client, _fake, _db = portal_app

    for i in range(_CAP):
        resp = _request_from(
            client, f"+99890000{i:04d}", {"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"}
        )
        assert resp.status_code == 204, f"request {i} should be under the cap"

    over = _request_from(
        client, "+998909999999", {"X-Forwarded-For": "10.0.0.99, 203.0.113.9"}
    )
    assert over.status_code == 429
    assert int(over.headers["Retry-After"]) > 0


def test_x_real_ip_keys_the_per_ip_bucket(portal_app) -> None:  # noqa: ANN001
    """Two different X-Real-IP values get independent buckets.

    The counterpart to the test above: the fix must not degrade into "ignore
    every header", which would collapse all traffic behind a proxy into a single
    bucket and rate-limit the whole internet as one caller.
    """
    client, _fake, _db = portal_app

    for i in range(_CAP):
        resp = _request_from(client, f"+99891000{i:04d}", {"X-Real-IP": "198.51.100.7"})
        assert resp.status_code == 204

    assert _request_from(
        client, "+998918888888", {"X-Real-IP": "198.51.100.7"}
    ).status_code == 429
    # A genuinely different client is unaffected by the first one's exhaustion.
    assert _request_from(
        client, "+998917777777", {"X-Real-IP": "198.51.100.8"}
    ).status_code == 204


# ── OTP verify ────────────────────────────────────────────────────────────────


def test_otp_verify_wrong_code_returns_400(portal_app) -> None:  # noqa: ANN001
    from app.domains.accounts.otp import OtpInvalid  # noqa: PLC0415

    client, _fake, _db = portal_app
    with patch("app.domains.accounts.api_portal.verify_code", side_effect=OtpInvalid("wrong")):
        resp = client.post(_VERIFY, json={"phone": _PHONE, "code": "000000"})
    assert resp.status_code == 400


def test_otp_verify_lockout_returns_429(portal_app) -> None:  # noqa: ANN001
    from app.domains.accounts.otp import OtpLocked  # noqa: PLC0415

    client, _fake, _db = portal_app
    with patch("app.domains.accounts.api_portal.verify_code", side_effect=OtpLocked("locked")):
        resp = client.post(_VERIFY, json={"phone": _PHONE, "code": "000000"})
    assert resp.status_code == 429


def test_otp_verify_success_issues_token_and_cookie(portal_app) -> None:  # noqa: ANN001
    from app.core.security import decode_token  # noqa: PLC0415

    client, _fake, _db = portal_app
    with patch("app.domains.accounts.api_portal.verify_code", return_value=_account(7)):
        resp = client.post(_VERIFY, json={"phone": _PHONE, "code": "123456"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["account"]["id"] == 7
    assert body["account"]["phone"] == _PHONE
    assert "portal_session=" in resp.headers.get("set-cookie", "")
    payload = decode_token(body["access_token"], expected_type="portal_access")
    assert payload["sub"] == "7"


def test_otp_verify_blocked_account_returns_403(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    with patch("app.domains.accounts.api_portal.verify_code", return_value=_account(8, status="blocked")):
        resp = client.post(_VERIFY, json={"phone": _PHONE, "code": "123456"})
    assert resp.status_code == 403


# ── get_current_account: audience isolation + blocked ─────────────────────────


def test_me_requires_auth(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    assert client.get(_ME).status_code == 401


def test_staff_token_rejected_by_portal_me(portal_app) -> None:  # noqa: ANN001
    from app.core.security import create_access_token  # noqa: PLC0415

    client, _fake, _db = portal_app
    staff = create_access_token(subject="1")
    resp = client.get(_ME, headers={"Authorization": f"Bearer {staff}"})
    assert resp.status_code == 401


def test_client_session_token_rejected_by_portal_me(portal_app) -> None:  # noqa: ANN001
    from app.core.security import create_client_session_token  # noqa: PLC0415

    client, _fake, _db = portal_app
    cs = create_client_session_token(subject="123456")
    resp = client.get(_ME, headers={"Authorization": f"Bearer {cs}"})
    assert resp.status_code == 401


def test_portal_token_rejected_by_staff_endpoint(portal_app) -> None:  # noqa: ANN001
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    client, _fake, _db = portal_app
    portal = create_portal_access_token(subject="7")
    resp = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {portal}"})
    assert resp.status_code == 401


def test_me_success_with_portal_token(portal_app) -> None:  # noqa: ANN001
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    client, _fake, db = portal_app
    db.query.return_value.filter.return_value.first.return_value = _account(7)
    token = create_portal_access_token(subject="7")
    resp = client.get(_ME, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == 7


def test_me_blocked_account_returns_403(portal_app) -> None:  # noqa: ANN001
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    client, _fake, db = portal_app
    db.query.return_value.filter.return_value.first.return_value = _account(7, status="blocked")
    token = create_portal_access_token(subject="7")
    resp = client.get(_ME, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_me_unknown_account_returns_401(portal_app) -> None:  # noqa: ANN001
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    client, _fake, db = portal_app
    db.query.return_value.filter.return_value.first.return_value = None
    token = create_portal_access_token(subject="999")
    resp = client.get(_ME, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ── refresh + logout ──────────────────────────────────────────────────────────


def test_refresh_rotates_cookie_and_returns_new_access_token(portal_app) -> None:  # noqa: ANN001
    from app.core.security import create_portal_refresh_token  # noqa: PLC0415

    client, _fake, db = portal_app
    db.query.return_value.filter.return_value.first.return_value = _account(7)
    old_refresh = create_portal_refresh_token(subject="7")

    resp = client.post(_REFRESH, headers={"Cookie": f"portal_session={old_refresh}"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]

    set_cookie = resp.headers.get("set-cookie", "")
    match = re.search(r"portal_session=([^;]+)", set_cookie)
    assert match is not None
    assert match.group(1) != old_refresh  # rotated: new jti ⇒ new token


def test_refresh_without_cookie_returns_401(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    assert client.post(_REFRESH).status_code == 401


def test_refresh_rejects_a_staff_refresh_token(portal_app) -> None:  # noqa: ANN001
    from app.core.security import create_refresh_token  # noqa: PLC0415

    client, _fake, _db = portal_app
    staff_refresh = create_refresh_token(subject="1")
    resp = client.post(_REFRESH, headers={"Cookie": f"portal_session={staff_refresh}"})
    assert resp.status_code == 401  # type mismatch: 'refresh' != 'portal_refresh'


def test_logout_clears_cookie(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    resp = client.post(_LOGOUT)
    assert resp.status_code == 200
    assert "portal_session=" in resp.headers.get("set-cookie", "")
