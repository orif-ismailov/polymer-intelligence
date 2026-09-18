"""Refresh-session state: rotation, reuse detection, revocation, step-up (IMEX-1).

The refresh token stays a JWT — `decode_token`'s type-claim contract is untouched —
but it is now only a CLAIM TICKET. A signature proves the token was minted here; it
does not prove the token is still the live one. That second question is the one this
module answers, and it is the question a stateless JWT structurally cannot: a signed
token is valid until it expires, so before this existed "rotation" meant issuing a new
cookie while the old one kept working, invalidation meant nothing, and logout was a
client-side gesture that cleared a cookie the server would still have honoured.

Two keys, both plain strings — no hashes, no Lua:

    rs:{fam}       JSON {kind, sub, jti, abs_exp, step_up_at, created_at}
                   TTL = min(sliding window, remaining absolute cap)
    rs:used:{jti}  the successor token that replaced this jti
                   TTL = REFRESH_ROTATION_GRACE_SECONDS

**Why no Lua.** Rotation needs one atomic step — deciding who gets to spend a given
token — and `SET … NX EX` is that step natively. The alternative, a compare-and-swap
Lua script, would also have to be emulated in `tests/_fake_redis.py`, and a test that
exercises a hand-written Lua interpreter is a test of the interpreter. The JSON
read-modify-write on `rs:{fam}` is not itself atomic and does not need to be: it is
only ever reached by the single caller that won the `SET NX`, so it is serialised by
construction.

**Why the grace window exists.** Two browser tabs refreshing at the same moment both
present the same valid token. Exactly one can win the claim; without a grace window the
loser looks identical to a thief replaying a stolen cookie, and the standard result is
a rotation scheme that signs people out at random and gets turned off. `rs:used:{jti}`
holds the winner's successor for a few seconds so the loser can be handed the same
token instead of an accusation. Past that window the same replay IS the incident.
"""

from __future__ import annotations

import dataclasses
import datetime
import json

import redis

from app.core.config import settings

#: Which surface a family belongs to. Staff and cabinet sessions share this machinery
#: but never each other's rows — `kind` is what a caller checks before trusting `sub`,
#: since staff_users.id 7 and user_accounts.id 7 are different people.
KIND_STAFF = "staff"
KIND_PORTAL = "portal"

_FAMILY_PREFIX = "rs:"
_USED_PREFIX = "rs:used:"


class SessionUnavailable(Exception):
    """Redis could not be reached. The session's fate is UNKNOWN, not decided.

    Callers answer 503. Answering 401 would sign every user on the platform out over
    an infrastructure blip — the one failure mode that turns a security improvement
    into an outage.
    """


class SessionInvalid(Exception):
    """Redis answered and the family is not there: logged out, expired, or revoked.

    Distinct from `SessionUnavailable` on purpose — this one IS decided, and the
    answer is 401.
    """


class SessionReused(Exception):
    """A refresh token was presented after it had already been spent.

    The family is revoked before this is raised. One of the two copies in circulation
    is an attacker's and we cannot tell which, so both lose.
    """


@dataclasses.dataclass(frozen=True, slots=True)
class SessionRecord:
    """The live state of one refresh-token family."""

    kind: str
    subject_id: int
    jti: str
    abs_exp: int
    step_up_at: int | None
    created_at: int


@dataclasses.dataclass(frozen=True, slots=True)
class RotateResult:
    """The outcome of spending a refresh token.

    `replayed` is False for the caller that won the claim and True for a second caller
    inside the grace window, whose `token` is the winner's successor. Both are success;
    the flag exists so the router sets the cookie it was given rather than the one it
    minted.
    """

    replayed: bool
    token: str | None = None


def _now() -> int:
    return int(datetime.datetime.now(datetime.UTC).timestamp())


def _family_key(fam: str) -> str:
    return f"{_FAMILY_PREFIX}{fam}"


def _used_key(jti: str) -> str:
    return f"{_USED_PREFIX}{jti}"


def _ttl_for(abs_exp: int) -> int:
    """Seconds until the family key should vanish: the sliding window, or the
    remaining absolute cap when that is nearer.

    Taking the minimum is what keeps a capped-out session from answering `current()`
    for the rest of its sliding window. At least 1 — Redis rejects a zero TTL, and a
    key that should already be gone is cheapest to let expire on its own next second.
    """
    remaining_cap = abs_exp - _now()
    sliding = settings.REFRESH_SESSION_TTL_DAYS * 86400
    return max(1, min(sliding, remaining_cap))


def _guard(exc: redis.RedisError) -> SessionUnavailable:
    return SessionUnavailable(str(exc))


def start(
    client: redis.Redis,  # type: ignore[type-arg]
    *,
    kind: str,
    subject_id: int,
    fam: str,
    jti: str,
    abs_exp: int,
) -> None:
    """Record a newly signed-in family. Overwrites any key at that id.

    `abs_exp` is fixed here and never moves again: it is copied into every successor
    token as the `abx` claim, so the ceiling survives rotation AND survives Redis
    losing the record entirely.

    `step_up_at` starts stamped, because a sign-in IS a password entry: asking again
    seconds later proves nothing and trains people to clear the prompt unread. It
    ages out on the ordinary schedule, and rotation never renews it — refreshing is
    not authenticating, which is what stops a stolen cookie from ever reaching a
    sensitive action.
    """
    now = _now()
    record = SessionRecord(
        kind=kind,
        subject_id=subject_id,
        jti=jti,
        abs_exp=abs_exp,
        step_up_at=now,
        created_at=now,
    )
    _store(client, fam, record)


def _store(client: redis.Redis, fam: str, record: SessionRecord) -> None:  # type: ignore[type-arg]
    payload = json.dumps(
        {
            "kind": record.kind,
            "sub": record.subject_id,
            "jti": record.jti,
            "abs_exp": record.abs_exp,
            "step_up_at": record.step_up_at,
            "created_at": record.created_at,
        }
    )
    try:
        client.set(_family_key(fam), payload, ex=_ttl_for(record.abs_exp))
    except redis.RedisError as exc:
        raise _guard(exc) from exc


def current(client: redis.Redis, fam: str) -> SessionRecord:  # type: ignore[type-arg]
    """The live state of `fam`, or `SessionInvalid` if there is none.

    A missing key is always a dead session and never "assume it is fine": fail closed
    is the property that makes revocation mean anything.
    """
    try:
        raw = client.get(_family_key(fam))
    except redis.RedisError as exc:
        raise _guard(exc) from exc

    if raw is None:
        raise SessionInvalid("no such session")

    try:
        data = json.loads(raw)
        return SessionRecord(
            kind=str(data["kind"]),
            subject_id=int(data["sub"]),
            jti=str(data["jti"]),
            abs_exp=int(data["abs_exp"]),
            step_up_at=None if data.get("step_up_at") is None else int(data["step_up_at"]),
            created_at=int(data["created_at"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        # A record we cannot read is a record we cannot trust. Treat it as absent
        # rather than guessing at defaults for fields that gate a security decision.
        raise SessionInvalid("unreadable session record") from exc


def rotate(
    client: redis.Redis,  # type: ignore[type-arg]
    *,
    fam: str,
    jti: str,
    new_jti: str,
    successor_token: str,
) -> RotateResult:
    """Spend `jti` and advance the family to `new_jti`.

    Raises `SessionInvalid` when the family is gone, and `SessionReused` — after
    revoking the family — when `jti` was spent longer ago than the grace window.
    """
    record = current(client, fam)

    if record.jti == jti:
        # The live token. Claim it; whoever wins the SET NX does the rotation.
        try:
            won = client.set(
                _used_key(jti),
                successor_token,
                nx=True,
                ex=settings.REFRESH_ROTATION_GRACE_SECONDS,
            )
        except redis.RedisError as exc:
            raise _guard(exc) from exc

        if won:
            _store(client, fam, dataclasses.replace(record, jti=new_jti))
            return RotateResult(replayed=False)

        # Lost a race decided between our read and our claim: another caller is
        # mid-rotation with this very token. Fall through and hand back its successor.

    # Not the live token: either superseded moments ago (forgivable) or long dead.
    try:
        successor = client.get(_used_key(jti))
    except redis.RedisError as exc:
        raise _guard(exc) from exc

    if successor is not None:
        return RotateResult(replayed=True, token=successor)

    revoke(client, fam)
    raise SessionReused("refresh token replayed after it was spent")


def revoke(client: redis.Redis, fam: str) -> None:  # type: ignore[type-arg]
    """Kill a family. Idempotent, and never raises.

    Both properties are load-bearing for the same caller: logout. A 503 there would
    leave a user who was told their session ended holding a cookie the server still
    honours, and the honest failure mode — the cookie is cleared client-side and the
    record expires on its own TTL — is strictly better than a scary error on the one
    action a worried user takes first.
    """
    try:
        client.delete(_family_key(fam))
    except redis.RedisError:
        return


def stamp_step_up(client: redis.Redis, fam: str) -> None:  # type: ignore[type-arg]
    """Open the step-up window for this family after a verified password re-entry."""
    record = current(client, fam)
    _store(client, fam, dataclasses.replace(record, step_up_at=_now()))


def has_recent_step_up(
    client: redis.Redis,  # type: ignore[type-arg]
    fam: str,
    *,
    within_seconds: int,
) -> bool:
    """Whether this family re-entered its password inside `within_seconds`.

    Raises `SessionInvalid` for a dead family rather than answering False. A sensitive
    action is exactly where the difference matters: False asks for a password, which a
    revoked session could supply all day without ever becoming authorised again.
    """
    record = current(client, fam)
    if record.step_up_at is None:
        return False
    return (_now() - record.step_up_at) <= within_seconds
