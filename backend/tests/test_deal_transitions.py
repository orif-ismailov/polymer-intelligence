"""
The deal state machine as pure data (P2 W1 — T1.2 acceptance).

Written BEFORE deal_service, per the plan: the transition matrix is the domain,
and it must be checkable without a database so the whole 10x10 pair space is
covered on every CI run.

Two independent rules are asserted here:
  * WHICH transitions exist (`VALID_TRANSITIONS`), over every ordered pair, and
  * WHO may drive one (`allowed_actors`) — a buyer cannot declare a shipment,
    a seller cannot confirm delivery, only staff may end a dispute, and the
    money-side statuses are reachable by `system` alone.

The expected matrix is spelled out in plain strings, independent of the
implementation, so a typo in the service cannot be "confirmed" by a test that
imports the thing it is checking. (`app.*` is imported inside the tests: the
conftest env patch is a session fixture and does not exist at collection time.)
"""

from __future__ import annotations

import itertools

#: The expected machine. Keys/values are the enum's string values.
EXPECTED: dict[str, set[str]] = {
    "negotiation": {"contract_pending", "cancelled"},
    # A declined or cancelled contract rolls the deal back to negotiation rather
    # than killing it — the parties may simply redraft.
    "contract_pending": {"contract_signed", "negotiation", "cancelled"},
    "contract_signed": {"payment_pending", "cancelled"},
    "payment_pending": {"paid_escrow", "disputed", "cancelled"},
    # FR-D8: once money sits in escrow, a unilateral cancel is no longer possible
    # — the way out is a dispute, which only staff can resolve.
    "paid_escrow": {"shipped", "disputed"},
    "shipped": {"delivered", "disputed"},
    "delivered": {"completed", "disputed"},
    "disputed": {"cancelled", "payment_pending", "paid_escrow", "shipped", "delivered"},
    "completed": set(),
    "cancelled": set(),
}


def _table() -> dict[str, set[str]]:
    """VALID_TRANSITIONS flattened to plain strings."""
    from app.services.deal_service import VALID_TRANSITIONS  # noqa: PLC0415

    return {
        frm.value: {to.value for to in targets} for frm, targets in VALID_TRANSITIONS.items()
    }


def _actors(frm: str, to: str) -> set[str]:
    from app.models.enums import DealStatus  # noqa: PLC0415
    from app.services.deal_service import allowed_actors  # noqa: PLC0415

    return {a.value for a in allowed_actors(DealStatus(frm), DealStatus(to))}


class TestTransitionMatrix:
    def test_covers_every_status(self) -> None:
        from app.models.enums import DealStatus  # noqa: PLC0415

        assert set(_table()) == {s.value for s in DealStatus} == set(EXPECTED), (
            "a status with no row in the table would raise KeyError at runtime"
        )

    def test_every_ordered_pair(self) -> None:
        table = _table()
        for frm, to in itertools.product(EXPECTED, EXPECTED):
            assert (to in table[frm]) is (to in EXPECTED[frm]), (
                f"{frm} → {to}: expected "
                f"{'allowed' if to in EXPECTED[frm] else 'rejected'}"
            )

    def test_terminal_states_are_dead_ends(self) -> None:
        table = _table()
        assert table["completed"] == set()
        assert table["cancelled"] == set()

    def test_no_self_transitions(self) -> None:
        table = _table()
        for status, targets in table.items():
            assert status not in targets, f"{status} → itself"

    def test_every_status_is_reachable_or_initial(self) -> None:
        """No orphan state: each status is negotiation or some transition's target."""
        table = _table()
        reachable = {t for targets in table.values() for t in targets}
        for status in table:
            assert status == "negotiation" or status in reachable, f"{status} unreachable"

    def test_staff_can_restore_every_disputable_status(self) -> None:
        """Whatever can enter a dispute must be restorable out of one.

        Deviation from the plan, deliberate: its disputed-exit set omitted
        payment_pending while still allowing entry from it, which would strand a
        deal disputed at payment_pending with no staff route back.
        """
        table = _table()
        enters = {frm for frm, targets in table.items() if "disputed" in targets}
        exits = table["disputed"]
        assert enters <= exits, f"no way back to {enters - exits}"


class TestActorRules:
    def test_only_the_seller_declares_a_shipment(self) -> None:
        assert _actors("paid_escrow", "shipped") == {"seller"}

    def test_only_the_buyer_confirms_delivery(self) -> None:
        assert _actors("shipped", "delivered") == {"buyer"}

    def test_either_side_may_cancel_or_dispute(self) -> None:
        assert {"buyer", "seller"} <= _actors("negotiation", "cancelled")
        assert {"buyer", "seller"} <= _actors("paid_escrow", "disputed")

    def test_money_and_signature_statuses_are_system_only(self) -> None:
        """These are consequences of events (contract activated, escrow opened,
        escrow funded, funds released) — never something a hand-written HTTP call
        may assert.

        `payment_pending` joined this list in P3: while there was no escrow, staff
        moved a signed deal on by hand; now `escrow_service.open_for_deal` does it
        together with creating the payment, so a deal can never be "awaiting
        payment" without an invoice behind it.

        Dispute resolution is excluded on purpose: staff RESTORING a deal to the
        status it already held is a different act from asserting that status for
        the first time, and it is staff-only by the rule above.
        """
        table = _table()
        for to in ("contract_signed", "payment_pending", "paid_escrow", "completed"):
            sources = [
                frm
                for frm, targets in table.items()
                if to in targets and frm != "disputed"
            ]
            assert sources, f"nothing reaches {to}"
            for frm in sources:
                assert _actors(frm, to) == {"system"}, f"{frm} → {to}"

    def test_only_staff_leaves_a_dispute(self) -> None:
        for to in _table()["disputed"]:
            assert _actors("disputed", to) == {"staff"}, f"disputed → {to} must be staff-only"
