"""Refresh-session state machine (IMEX-1).

The refresh JWT is only a claim ticket: it is worthless unless Redis says its `jti`
is the live one for its family. Everything the ticket asks for that a stateless JWT
could not give us is decided here — rotation, invalidation of the predecessor, reuse
detection, logout revocation, and the step-up window.

Three properties are the whole point of the design and are asserted rather than left
to review:

* **Rotation invalidates.** The token that was just spent is dead; presenting it again
  past the grace window kills every sibling in its family.
* **Concurrent tabs are not thieves.** Two refreshes racing on the same token is the
  ordinary case, not an attack, and it must not log anyone out. Within the grace
  window the second caller gets the *same* successor back.
* **A missing key is a dead session, an unreachable Redis is not.** The first is 401,
  the second is 503 — an infrastructure blip must not destroy every session on the
  platform.
"""

from __future__ import annotations

import datetime
import json

import pytest
import redis

from app.services import session_service as svc
from tests._fake_redis import FakeRedis

_FAM = "fam0123456789abcdef"
_JTI = "jti-one"
_NEW_JTI = "jti-two"
_TOKEN = "successor.jwt.value"


def _now() -> int:
    return int(datetime.datetime.now(datetime.UTC).timestamp())


def _abs_exp(days: int = 90) -> int:
    return _now() + days * 86400


class BrokenRedis(FakeRedis):
    """A Redis that is reachable by the type checker and by nothing else."""

    def set(self, *args: object, **kwargs: object) -> bool | None:
        raise redis.ConnectionError("connection refused")

    def setex(self, *args: object, **kwargs: object) -> bool:
        raise redis.ConnectionError("connection refused")

    def get(self, *args: object, **kwargs: object) -> str | None:
        raise redis.ConnectionError("connection refused")

    def delete(self, *args: object, **kwargs: object) -> int:
        raise redis.ConnectionError("connection refused")


def _start(fake: FakeRedis, *, abs_exp: int | None = None) -> None:
    svc.start(
        fake,
        kind=svc.KIND_PORTAL,
        subject_id=42,
        fam=_FAM,
        jti=_JTI,
        abs_exp=abs_exp if abs_exp is not None else _abs_exp(),
    )


# ── start / current ───────────────────────────────────────────────────────────


def test_start_records_the_family_and_current_reads_it_back() -> None:
    fake = FakeRedis()
    _start(fake)

    record = svc.current(fake, _FAM)

    assert record.kind == svc.KIND_PORTAL
    assert record.subject_id == 42
    assert record.jti == _JTI


def test_current_raises_session_invalid_when_the_family_is_absent() -> None:
    with pytest.raises(svc.SessionInvalid):
        svc.current(FakeRedis(), "fam-that-was-never-started")


def test_start_expires_the_family_at_the_absolute_cap_when_it_is_nearer() -> None:
    """A session 2 days from its 90-day cap gets a 2-day TTL, not a 30-day one.

    Without this the key outlives the cap and the only thing still enforcing the
    90 days is the `abx` claim — which is correct, but leaves a revoked-by-time
    family answering `current()` for 28 days.
    """
    fake = FakeRedis()
    _start(fake, abs_exp=_now() + 2 * 86400)

    assert fake.ttls[f"rs:{_FAM}"] <= 2 * 86400


# ── rotation ──────────────────────────────────────────────────────────────────


def test_rotate_advances_the_family_to_the_new_jti() -> None:
    fake = FakeRedis()
    _start(fake)

    result = svc.rotate(
        fake, fam=_FAM, jti=_JTI, new_jti=_NEW_JTI, successor_token=_TOKEN
    )

    assert result.replayed is False
    assert svc.current(fake, _FAM).jti == _NEW_JTI


def test_rotate_refuses_a_jti_that_is_not_the_live_one() -> None:
    """A token from the same family but not the current one, never spent, never
    stored as a successor: the only way to hold it is to have kept a copy."""
    fake = FakeRedis()
    _start(fake)

    with pytest.raises(svc.SessionReused):
        svc.rotate(
            fake, fam=_FAM, jti="some-older-jti", new_jti=_NEW_JTI, successor_token=_TOKEN
        )


def test_reuse_revokes_the_whole_family() -> None:
    fake = FakeRedis()
    _start(fake)

    with pytest.raises(svc.SessionReused):
        svc.rotate(
            fake, fam=_FAM, jti="stolen", new_jti=_NEW_JTI, successor_token=_TOKEN
        )

    with pytest.raises(svc.SessionInvalid):
        svc.current(fake, _FAM)


def test_a_second_refresh_within_the_grace_window_returns_the_same_successor() -> None:
    """Two tabs refreshing at once is the ordinary case. The loser of the race must
    get the winner's token back, not a 401 — this is the single thing that separates
    a rotation scheme that works from one that randomly signs people out."""
    fake = FakeRedis()
    _start(fake)

    first = svc.rotate(
        fake, fam=_FAM, jti=_JTI, new_jti=_NEW_JTI, successor_token=_TOKEN
    )
    second = svc.rotate(
        fake, fam=_FAM, jti=_JTI, new_jti="jti-three", successor_token="another.jwt"
    )

    assert first.replayed is False
    assert second.replayed is True
    assert second.token == _TOKEN
    assert svc.current(fake, _FAM).jti == _NEW_JTI  # the loser did not advance it


def test_replaying_a_spent_token_after_the_grace_window_is_reuse() -> None:
    fake = FakeRedis()
    _start(fake)
    svc.rotate(fake, fam=_FAM, jti=_JTI, new_jti=_NEW_JTI, successor_token=_TOKEN)

    # The grace key is what makes a replay forgivable; its expiry is what makes the
    # same replay an incident. Expire it by hand rather than sleeping 10 seconds.
    fake.delete(f"rs:used:{_JTI}")

    with pytest.raises(svc.SessionReused):
        svc.rotate(
            fake, fam=_FAM, jti=_JTI, new_jti="jti-four", successor_token="another.jwt"
        )


def test_rotate_raises_session_invalid_when_the_family_is_gone() -> None:
    """Logout, an expired cap, or a family killed by a sibling's reuse."""
    fake = FakeRedis()

    with pytest.raises(svc.SessionInvalid):
        svc.rotate(
            fake, fam=_FAM, jti=_JTI, new_jti=_NEW_JTI, successor_token=_TOKEN
        )


def test_rotate_preserves_the_absolute_cap_in_the_record() -> None:
    """Rotation must not extend the 90-day ceiling — sliding is 30 days at a time,
    the cap is fixed at first sign-in."""
    fake = FakeRedis()
    cap = _now() + 3 * 86400
    _start(fake, abs_exp=cap)

    svc.rotate(fake, fam=_FAM, jti=_JTI, new_jti=_NEW_JTI, successor_token=_TOKEN)

    assert svc.current(fake, _FAM).abs_exp == cap


# ── revocation ────────────────────────────────────────────────────────────────


def test_revoke_kills_the_family() -> None:
    fake = FakeRedis()
    _start(fake)

    svc.revoke(fake, _FAM)

    with pytest.raises(svc.SessionInvalid):
        svc.current(fake, _FAM)


def test_revoke_is_idempotent() -> None:
    """Logout must never fail because the session was already gone."""
    svc.revoke(FakeRedis(), "fam-that-was-never-started")


# ── step-up ───────────────────────────────────────────────────────────────────


def test_signing_in_counts_as_the_step_up() -> None:
    """A password typed thirty seconds ago at the login form IS re-authentication.

    Not a convenience: without it the registration wizard stops mid-flow to ask a
    brand-new user for the password they just typed, on the bank step — and a prompt
    that appears when nothing suspicious is happening is one people learn to clear
    without reading, which is the failure mode step-up exists to avoid.
    """
    fake = FakeRedis()
    _start(fake)

    assert svc.has_recent_step_up(fake, _FAM, within_seconds=300) is True


def test_the_sign_in_credit_expires_like_any_other() -> None:
    """It is a stamp, not an exemption — an hour-old session is asked again."""
    fake = FakeRedis()
    _start(fake)

    record = json.loads(fake.store[f"rs:{_FAM}"])
    record["step_up_at"] = _now() - 3600
    fake.store[f"rs:{_FAM}"] = json.dumps(record)

    assert svc.has_recent_step_up(fake, _FAM, within_seconds=300) is False


def test_rotation_does_not_renew_the_step_up_credit() -> None:
    """Refreshing is not authenticating. A stolen cookie refreshed for a month must
    never accumulate its way into a sensitive action — only a password does that."""
    fake = FakeRedis()
    _start(fake)
    record = json.loads(fake.store[f"rs:{_FAM}"])
    record["step_up_at"] = _now() - 3600
    fake.store[f"rs:{_FAM}"] = json.dumps(record)

    svc.rotate(fake, fam=_FAM, jti=_JTI, new_jti=_NEW_JTI, successor_token=_TOKEN)

    assert svc.has_recent_step_up(fake, _FAM, within_seconds=300) is False


def test_stamp_step_up_opens_the_window() -> None:
    fake = FakeRedis()
    _start(fake)

    svc.stamp_step_up(fake, _FAM)

    assert svc.has_recent_step_up(fake, _FAM, within_seconds=300) is True


def test_the_step_up_window_closes() -> None:
    fake = FakeRedis()
    _start(fake)
    svc.stamp_step_up(fake, _FAM)

    # Age the stamp past the window rather than sleeping.
    record = json.loads(fake.store[f"rs:{_FAM}"])
    record["step_up_at"] = _now() - 3600
    fake.store[f"rs:{_FAM}"] = json.dumps(record)

    assert svc.has_recent_step_up(fake, _FAM, within_seconds=300) is False


def test_step_up_survives_rotation() -> None:
    """The stamp lives in the family record, not in a token, so a refresh in the
    middle of a sensitive flow does not send the user back to the password prompt."""
    fake = FakeRedis()
    _start(fake)
    svc.stamp_step_up(fake, _FAM)

    svc.rotate(fake, fam=_FAM, jti=_JTI, new_jti=_NEW_JTI, successor_token=_TOKEN)

    assert svc.has_recent_step_up(fake, _FAM, within_seconds=300) is True


def test_has_recent_step_up_raises_session_invalid_for_a_dead_family() -> None:
    """A sensitive action is the one place worth telling a revoked session apart
    from an un-stepped-up one: 401 sends it to sign in, 403 only asks for a password
    the dead session could never use."""
    with pytest.raises(svc.SessionInvalid):
        svc.has_recent_step_up(FakeRedis(), _FAM, within_seconds=300)


# ── degradation ───────────────────────────────────────────────────────────────


def test_an_unreachable_redis_is_service_unavailable_not_an_invalid_session() -> None:
    """401 would sign every user on the platform out over an infrastructure blip."""
    broken = BrokenRedis()

    with pytest.raises(svc.SessionUnavailable):
        svc.current(broken, _FAM)

    with pytest.raises(svc.SessionUnavailable):
        svc.rotate(
            broken, fam=_FAM, jti=_JTI, new_jti=_NEW_JTI, successor_token=_TOKEN
        )

    with pytest.raises(svc.SessionUnavailable):
        svc.start(
            broken,
            kind=svc.KIND_PORTAL,
            subject_id=42,
            fam=_FAM,
            jti=_JTI,
            abs_exp=_abs_exp(),
        )


def test_revoke_swallows_an_unreachable_redis() -> None:
    """Logout is the one caller that must not fail: a 503 here leaves the user
    holding a cookie they were told was cleared. The cookie is cleared regardless,
    and the session dies with its TTL."""
    svc.revoke(BrokenRedis(), _FAM)
