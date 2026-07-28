"""Normalized escrow provider events (R6 / P7.b — T1.1).

The partner bank is not chosen yet and its callback format is unknown. What IS
known is our own side of the conversation: there is an `EscrowPayment`, it has a
`provider_ref`, and it moves `pending → funded → released/refunded`. So the
contract is written from OUR shape inward, and each bank becomes one mapper
function in `MAPPERS`.

`generic` is that shape spelled out — it is a real provider, not a placeholder:
a bank able to POST our field names needs no adapter at all, and the escrow
sandbox / integration rehearsals run against it.

Boundary rule: nothing here imports a domain model. The normalized status is a
plain string from `KNOWN_STATUSES`; turning it into an `EscrowStatus` is the
service's job, and a test asserts the two sets have not drifted apart.

Two details that look small and are not:

  * **`extract_external_id` runs before `normalize`.** The webhook route writes
    the raw inbox row first and parses afterwards, so the idempotency key has to
    be derivable from a payload we may not understand. Falling back to a hash of
    the body means a bank that retries an unreadable callback still collides on
    `UNIQUE (provider, external_id)` instead of piling up duplicates.
  * **`KNOWN_STATUSES` is closed.** A bank reporting `partially_funded` raises
    here, which lands the event in the operator queue with a readable reason,
    rather than reaching a state machine that would refuse it anonymously.
"""

from __future__ import annotations

import datetime
import decimal
import hashlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: The normalized status vocabulary — mirrors `EscrowStatus` verbatim (asserted
#: by a test) without importing it, so the gateway stays free of domain models.
STATUS_PENDING = "pending"
STATUS_FUNDED = "funded"
STATUS_RELEASED = "released"
STATUS_REFUNDED = "refunded"

KNOWN_STATUSES: frozenset[str] = frozenset(
    {STATUS_PENDING, STATUS_FUNDED, STATUS_RELEASED, STATUS_REFUNDED}
)

#: Our own callback contract. A bank that can post these field names needs no
#: adapter; every other bank gets a mapper next to this one.
PROVIDER_GENERIC = "generic"


class UnknownProvider(Exception):
    """No mapper is registered for this provider."""


class MalformedEvent(Exception):
    """The payload is missing a required field, or carries one we cannot use."""


@dataclass(frozen=True)
class NormalizedEscrowEvent:
    """What a provider told us, in our vocabulary.

    `amount`/`currency` are optional because not every bank echoes them — but
    when they ARE present the service compares them with the payment and holds
    on a mismatch, which is how a partial payment surfaces as an operator
    question instead of a silently-accepted `funded`.
    """

    external_id: str
    provider_ref: str
    status: str
    amount: decimal.Decimal | None = None
    currency: str | None = None
    occurred_at: datetime.datetime | None = None
    #: The provider's own status string, kept verbatim for the evidence row.
    raw_status: str = ""


# ── field helpers ─────────────────────────────────────────────────────────────


def _required_str(payload: Mapping[str, Any], *names: str) -> str:
    """First non-blank string among `names`, or `MalformedEvent`."""
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise MalformedEvent(f"missing required field: {' | '.join(names)}")


def _optional_amount(payload: Mapping[str, Any], *names: str) -> decimal.Decimal | None:
    for name in names:
        value = payload.get(name)
        if value is None or value == "":
            continue
        try:
            return decimal.Decimal(str(value))
        except (decimal.InvalidOperation, ValueError) as exc:
            raise MalformedEvent(f"{name} is not a number: {value!r}") from exc
    return None


def _optional_dt(payload: Mapping[str, Any], *names: str) -> datetime.datetime | None:
    """Parse an ISO-8601 timestamp; a naive one is read as UTC.

    A timestamp we cannot parse is dropped rather than fatal — it is metadata,
    and refusing the whole event over a formatting quirk would strand real money
    movement in the inbox.
    """
    for name in names:
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            parsed = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            logger.warning("escrow.event.bad_timestamp", extra={"field": name, "value": value})
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=datetime.UTC)
        return parsed
    return None


def _status(payload: Mapping[str, Any], *names: str) -> tuple[str, str]:
    """(normalized, verbatim) status, or `MalformedEvent` for anything unmodelled."""
    raw = _required_str(payload, *names)
    normalized = raw.strip().lower()
    if normalized not in KNOWN_STATUSES:
        raise MalformedEvent(f"unmodelled status: {raw!r}")
    return normalized, raw


# ── mappers ───────────────────────────────────────────────────────────────────


def _generic(payload: Mapping[str, Any]) -> NormalizedEscrowEvent:
    """Our own contract. Alternative field names are accepted where a bank is
    overwhelmingly likely to use them (`reference` for the escrow handle), but
    nothing is guessed: an absent required field is an error, not a default."""
    status, raw_status = _status(payload, "status", "state")
    return NormalizedEscrowEvent(
        external_id=_required_str(payload, "event_id", "id"),
        provider_ref=_required_str(payload, "escrow_ref", "provider_ref", "reference"),
        status=status,
        amount=_optional_amount(payload, "amount"),
        currency=(payload.get("currency") or "").strip().upper() or None,
        occurred_at=_optional_dt(payload, "occurred_at", "timestamp"),
        raw_status=raw_status,
    )


#: provider name → mapper. One entry today; a real bank is one function more.
MAPPERS: dict[str, Callable[[Mapping[str, Any]], NormalizedEscrowEvent]] = {
    PROVIDER_GENERIC: _generic,
}

#: Where each provider carries its own event id, for the pre-parse key.
_ID_FIELDS: dict[str, tuple[str, ...]] = {
    PROVIDER_GENERIC: ("event_id", "id"),
}


# ── public API ────────────────────────────────────────────────────────────────


def extract_external_id(provider: str, payload: object, raw: bytes) -> str:
    """The idempotency key for a callback we have not parsed yet.

    Never raises: it is called on the request path, before the raw inbox row is
    written, and an unreadable callback must still be storable. When the
    provider supplies no usable id, the body hash stands in — a retry of the
    same bytes collides on `UNIQUE (provider, external_id)`, which is the
    guarantee we actually need.
    """
    fields = _ID_FIELDS.get(provider, ())
    if isinstance(payload, Mapping):
        for name in fields:
            value = payload.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int):
                return str(value)
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def normalize(provider: str, payload: object) -> NormalizedEscrowEvent:
    """Map a provider payload into our vocabulary.

    Raises `UnknownProvider` when nobody has written a mapper, `MalformedEvent`
    when the payload cannot be read. Both land the event in the operator queue
    with the reason attached — see `escrow_service.apply_provider_event`.
    """
    mapper = MAPPERS.get(provider)
    if mapper is None:
        raise UnknownProvider(provider)
    if not isinstance(payload, Mapping):
        raise MalformedEvent(f"payload is {type(payload).__name__}, expected an object")
    return mapper(payload)
