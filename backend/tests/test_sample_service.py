"""
The sample-request state machine as a table (P6 W3 — T3.1). No database.

Unlike the lab machine, both sides drive this one, and that is the whole point
of the table: the seller says whether a sample goes out, the buyer says whether
it arrived. Neither may speak for the other — a seller who could mark a parcel
`received` would close their own dispute, and a buyer who could mark it `sent`
would invent a shipment.

    requested ──accepted(seller)──► accepted ──sent(seller)──► sent
        └──────declined(seller)──► declined      sent ──received(buyer)──────► received
                                                      └─rejected_by_buyer(buyer)─►

Statuses are spelled as strings and every `app.*` import happens inside a test:
importing `app.models.enums` at module scope pulls in the whole `app.models`
package and builds `settings` from the ambient environment before conftest's
session-scoped env patch runs (see `test_lab_service.py` for the symptom).
"""

from __future__ import annotations

import pytest

#: from → the statuses reachable from it.
EXPECTED: dict[str, set[str]] = {
    "requested": {"accepted", "declined"},
    "accepted": {"sent"},
    "sent": {"received", "rejected_by_buyer"},
    "declined": set(),
    "received": set(),
    "rejected_by_buyer": set(),
}

#: to → the party allowed to make that move.
ACTORS: dict[str, str] = {
    "accepted": "seller",
    "declined": "seller",
    "sent": "seller",
    "received": "buyer",
    "rejected_by_buyer": "buyer",
}

ALL_STATUSES = list(EXPECTED)


def _samples():  # noqa: ANN202
    from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415

    return sample_service


def _status(name: str):  # noqa: ANN202
    from app.models.enums import SampleRequestStatus  # noqa: PLC0415

    return SampleRequestStatus(name)


class TestTransitionTable:
    def test_the_table_matches_the_specification(self) -> None:
        table = {
            str(frm): {str(t) for t in targets}
            for frm, targets in _samples()._TRANSITIONS.items()
        }
        assert table == EXPECTED

    def test_every_status_has_an_entry(self) -> None:
        from app.models.enums import SampleRequestStatus  # noqa: PLC0415

        assert set(_samples()._TRANSITIONS) == set(SampleRequestStatus)

    @pytest.mark.parametrize(
        ("frm", "to"),
        [(f, t) for f, targets in EXPECTED.items() for t in targets],
    )
    def test_allowed_pairs_are_allowed(self, frm: str, to: str) -> None:
        assert _samples().can_transition(_status(frm), _status(to))

    @pytest.mark.parametrize(
        ("frm", "to"),
        [
            (f, t)
            for f in EXPECTED
            for t in ALL_STATUSES
            if t not in EXPECTED[f] and t != f
        ],
    )
    def test_everything_else_is_refused(self, frm: str, to: str) -> None:
        assert not _samples().can_transition(_status(frm), _status(to))

    def test_a_declined_request_is_final(self) -> None:
        """Asking again is a NEW request — that is what the partial unique index
        frees the slot for."""
        assert _samples()._TRANSITIONS[_status("declined")] == set()

    def test_the_happy_path_is_walkable_end_to_end(self) -> None:
        path = ["requested", "accepted", "sent", "received"]
        for frm, to in zip(path, path[1:], strict=False):
            assert _samples().can_transition(_status(frm), _status(to)), f"{frm} → {to}"


class TestWhoMayMove:
    @pytest.mark.parametrize(("to", "role"), list(ACTORS.items()))
    def test_the_right_party_may_move(self, to: str, role: str) -> None:
        assert _samples().actor_for(_status(to)) == role

    @pytest.mark.parametrize(("to", "role"), list(ACTORS.items()))
    def test_the_other_party_may_not(self, to: str, role: str) -> None:
        other = "buyer" if role == "seller" else "seller"
        assert _samples().actor_for(_status(to)) != other

    def test_a_seller_cannot_confirm_a_delivery_they_made(self) -> None:
        """The named failure: it would let a seller close their own dispute."""
        assert _samples().actor_for(_status("received")) == "buyer"

    def test_a_buyer_cannot_invent_a_shipment(self) -> None:
        assert _samples().actor_for(_status("sent")) == "seller"


class TestAvailableTransitions:
    """The portal renders each side's buttons from this, so neither side is ever
    shown a move the API would refuse."""

    def test_the_seller_sees_accept_and_decline_on_a_new_request(self) -> None:
        assert [
            str(s)
            for s in _samples().available_transitions(_status("requested"), "seller")
        ] == ["accepted", "declined"]

    def test_the_buyer_sees_nothing_on_a_new_request(self) -> None:
        assert _samples().available_transitions(_status("requested"), "buyer") == []

    def test_the_buyer_confirms_or_rejects_what_arrived(self) -> None:
        assert [
            str(s) for s in _samples().available_transitions(_status("sent"), "buyer")
        ] == ["received", "rejected_by_buyer"]

    def test_a_finished_request_offers_nothing_to_anyone(self) -> None:
        for name in ("declined", "received", "rejected_by_buyer"):
            for role in ("buyer", "seller"):
                assert _samples().available_transitions(_status(name), role) == []


class TestFieldRules:
    def test_shipping_requires_a_courier_and_a_tracking_reference(self) -> None:
        """FR-L3. "It's on its way" with nothing to track is not a shipment."""
        assert _status("sent") in _samples().SHIPMENT_REQUIRED

    def test_saying_no_requires_a_reason(self) -> None:
        for name in ("declined", "rejected_by_buyer"):
            assert _status(name) in _samples().REASON_REQUIRED
