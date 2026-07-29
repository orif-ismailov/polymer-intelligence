"""Normalized escrow provider events (R6 / P7.b — T1.1).

The bank is unknown, but the SHAPE of what it must tell us is not: which
operation, which escrow, what happened, how much. This module is that shape plus
a per-provider mapper registry — adding a real bank is one function, not a
rewrite of the payments domain.

Two things these tests pin down that are easy to get wrong later:

  * the idempotency key is extracted BEFORE the payload is understood, because
    the raw inbox is written before anything is parsed — a callback we cannot
    read is still evidence, and a retry of it must still collide;
  * the normalized status set is closed. A bank inventing `partially_funded`
    must fail loudly here rather than arrive at the state machine as something
    it will silently refuse later.

Imports of `app.*` live inside the test bodies on purpose: importing them at
module scope pulls in `app.core.config` at COLLECTION time, before the
session-scoped `patch_env` fixture runs, which builds `settings` from the
ambient environment and breaks unrelated suites (learned the hard way in P6).
"""

from __future__ import annotations

import hashlib
import json

import pytest

# ── extract_external_id — the pre-parse idempotency key ──────────────────────


def test_external_id_uses_the_providers_own_event_id() -> None:
    from app.integrations.escrow import events

    body = {"event_id": "bank-op-77", "escrow_ref": "E-1", "status": "funded"}
    raw = json.dumps(body).encode()

    assert events.extract_external_id("generic", body, raw) == "bank-op-77"


def test_external_id_falls_back_to_a_body_hash_when_the_provider_gives_none() -> None:
    """No id in the payload → the body itself is the key, so a retry collides."""
    from app.integrations.escrow import events

    body = {"escrow_ref": "E-1", "status": "funded"}
    raw = json.dumps(body).encode()

    key = events.extract_external_id("generic", body, raw)

    assert key == f"sha256:{hashlib.sha256(raw).hexdigest()}"
    # Same body, delivered twice → same key.
    assert events.extract_external_id("generic", body, raw) == key


def test_external_id_survives_an_unparseable_body() -> None:
    """An unknown provider or a non-dict payload must still yield a key.

    The route records first and parses later; if this raised, an unreadable
    callback could not be stored at all.
    """
    from app.integrations.escrow import events

    raw = b"<xml>not json</xml>"
    key = events.extract_external_id("mystery-bank", None, raw)

    assert key == f"sha256:{hashlib.sha256(raw).hexdigest()}"


def test_external_id_ignores_a_blank_event_id() -> None:
    from app.integrations.escrow import events

    raw = b'{"event_id": "   ", "escrow_ref": "E-1", "status": "funded"}'
    key = events.extract_external_id("generic", json.loads(raw), raw)

    assert key.startswith("sha256:")


# ── normalize — the generic mapper ───────────────────────────────────────────


def test_generic_mapper_normalizes_a_full_payload() -> None:
    from app.integrations.escrow import events

    payload = {
        "event_id": "bank-op-77",
        "escrow_ref": "ESC-2026-0001",
        "status": "FUNDED",
        "amount": "25000.00",
        "currency": "uzs",
        "occurred_at": "2026-07-28T09:15:00+00:00",
    }

    event = events.normalize("generic", payload)

    assert event.external_id == "bank-op-77"
    assert event.provider_ref == "ESC-2026-0001"
    assert event.status == events.STATUS_FUNDED
    assert str(event.amount) == "25000.00"
    assert event.currency == "UZS"
    assert event.occurred_at is not None
    assert event.occurred_at.tzinfo is not None
    # What the bank said verbatim, kept for the evidence row.
    assert event.raw_status == "FUNDED"


def test_generic_mapper_tolerates_a_bank_that_omits_the_optionals() -> None:
    """Amount/currency/timestamp are nice-to-have; ref and status are not."""
    from app.integrations.escrow import events

    event = events.normalize(
        "generic", {"event_id": "e1", "escrow_ref": "E-1", "status": "released"}
    )

    assert event.status == events.STATUS_RELEASED
    assert event.amount is None
    assert event.currency is None
    assert event.occurred_at is None


@pytest.mark.parametrize(
    "payload",
    [
        {"escrow_ref": "E-1", "status": "funded"},                 # no event id
        {"event_id": "e1", "status": "funded"},                    # no escrow ref
        {"event_id": "e1", "escrow_ref": "E-1"},                   # no status
        {"event_id": "e1", "escrow_ref": "E-1", "status": ""},     # blank status
        {"event_id": "e1", "escrow_ref": " ", "status": "funded"}, # blank ref
    ],
)
def test_generic_mapper_rejects_a_payload_missing_a_required_field(payload: dict) -> None:
    from app.integrations.escrow import events

    with pytest.raises(events.MalformedEvent):
        events.normalize("generic", payload)


def test_generic_mapper_rejects_a_status_outside_the_closed_set() -> None:
    """`partially_funded` is a real banking concept we do not model yet.

    Failing here puts it in the operator's queue with a readable reason instead
    of letting it reach a state machine that would refuse it anonymously.
    """
    from app.integrations.escrow import events

    with pytest.raises(events.MalformedEvent):
        events.normalize(
            "generic", {"event_id": "e1", "escrow_ref": "E-1", "status": "partially_funded"}
        )


def test_generic_mapper_rejects_an_unparseable_amount() -> None:
    from app.integrations.escrow import events

    with pytest.raises(events.MalformedEvent):
        events.normalize(
            "generic",
            {"event_id": "e1", "escrow_ref": "E-1", "status": "funded", "amount": "lots"},
        )


def test_normalize_rejects_a_provider_with_no_mapper() -> None:
    from app.integrations.escrow import events

    with pytest.raises(events.UnknownProvider):
        events.normalize("kapitalbank", {"event_id": "e1"})


def test_normalize_rejects_a_non_dict_payload() -> None:
    from app.integrations.escrow import events

    with pytest.raises(events.MalformedEvent):
        events.normalize("generic", ["not", "a", "mapping"])


# ── the registry itself ──────────────────────────────────────────────────────


def test_only_the_generic_provider_ships_today() -> None:
    """A real bank is one mapper away — and its absence must be explicit.

    If this fails because a bank was added, add it to the assertion; the point
    is that nobody adds a provider without noticing they have to.
    """
    from app.integrations.escrow import events

    assert set(events.MAPPERS) == {events.PROVIDER_GENERIC}


def test_the_status_set_matches_the_escrow_state_machine() -> None:
    """The normalized statuses are exactly the EscrowStatus values.

    They are separate strings on purpose (the gateway does not import domain
    models), so something has to assert they have not drifted apart.
    """
    from app.integrations.escrow import events
    from app.models.enums import EscrowStatus

    assert {s.value for s in EscrowStatus} == events.KNOWN_STATUSES
