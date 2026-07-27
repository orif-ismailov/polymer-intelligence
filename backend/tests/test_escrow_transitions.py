"""
The escrow state machine as pure data (P3 W1 — T1.2 acceptance).

Written BEFORE escrow_service, like the deal matrix in P2: money states are the
domain, and the whole 4x4 ordered-pair space must be checkable without a
database so every CI run covers it.

The escrow machine is deliberately smaller than the deal's. It answers one
question — where is the money — and its two terminal states are terminal for a
reason: a released or refunded payment is a completed bank operation, and
"undoing" one is a NEW payment, not a status edit.

The expected matrix is spelled out in plain strings, independent of the
implementation, so a typo in the service cannot be "confirmed" by a test that
imports the thing it is checking. (`app.*` is imported inside the tests: the
conftest env patch is a session fixture and does not exist at collection time.)
"""

from __future__ import annotations

import itertools

#: The expected machine. Keys/values are the enum's string values.
EXPECTED: dict[str, set[str]] = {
    # An invoice was issued. Either the money arrives, or the deal dies and the
    # (never-received) escrow is closed as refunded.
    "pending": {"funded", "refunded"},
    # The money is held. It goes to the seller, or back to the buyer.
    "funded": {"released", "refunded"},
    "released": set(),
    "refunded": set(),
}

#: Which deal status each escrow move asserts. This is the whole point of the
#: module: `paid_escrow` and `completed` exist on the deal ONLY as consequences
#: of money moving, which is why neither is reachable from an HTTP handler.
EXPECTED_DEAL_EFFECT: dict[str, str] = {
    "funded": "paid_escrow",
    "released": "completed",
    "refunded": "cancelled",
}


def _table() -> dict[str, set[str]]:
    """_TRANSITIONS flattened to plain strings."""
    from app.services.escrow_service import _TRANSITIONS  # noqa: PLC0415

    return {frm.value: {to.value for to in tos} for frm, tos in _TRANSITIONS.items()}


class TestTransitionMatrix:
    def test_covers_every_status(self) -> None:
        from app.models.enums import EscrowStatus  # noqa: PLC0415

        assert set(_table()) == {s.value for s in EscrowStatus} == set(EXPECTED), (
            "a status with no row in the table would raise KeyError at runtime"
        )

    def test_every_ordered_pair(self) -> None:
        table = _table()
        for frm, to in itertools.product(EXPECTED, EXPECTED):
            assert (to in table[frm]) is (to in EXPECTED[frm]), (
                f"{frm} → {to}: expected "
                f"{'allowed' if to in EXPECTED[frm] else 'rejected'}"
            )

    def test_completed_operations_are_terminal(self) -> None:
        """A released or refunded payment is a finished bank operation; reversing
        one is a NEW payment, never a status edit."""
        table = _table()
        assert table["released"] == set()
        assert table["refunded"] == set()

    def test_no_self_transitions(self) -> None:
        for status, targets in _table().items():
            assert status not in targets, f"{status} → itself"

    def test_money_cannot_be_released_without_arriving_first(self) -> None:
        assert "released" not in _table()["pending"], (
            "paying the seller out of an unfunded escrow is the one thing this "
            "machine exists to prevent"
        )


class TestDealEffects:
    def test_every_move_drags_the_deal(self) -> None:
        """No escrow move is silent: each one asserts a deal status, in the same
        transaction (see the DB suite)."""
        from app.services.escrow_service import _DEAL_EFFECT  # noqa: PLC0415

        assert {
            status.value: deal_status.value for status, deal_status in _DEAL_EFFECT.items()
        } == EXPECTED_DEAL_EFFECT

    def test_the_effects_are_real_deal_transitions(self) -> None:
        """The deal statuses escrow asserts must be reachable from where the deal
        actually is when the money moves — otherwise `mark` would always 409."""
        from app.models.enums import DealStatus  # noqa: PLC0415
        from app.services.deal_service import VALID_TRANSITIONS  # noqa: PLC0415

        assert DealStatus.paid_escrow in VALID_TRANSITIONS[DealStatus.payment_pending]
        assert DealStatus.completed in VALID_TRANSITIONS[DealStatus.delivered]
        assert DealStatus.cancelled in VALID_TRANSITIONS[DealStatus.payment_pending]
        assert DealStatus.cancelled in VALID_TRANSITIONS[DealStatus.disputed]

    def test_a_refund_out_of_live_escrow_needs_a_dispute_first(self) -> None:
        """FR-D8 in the money path: once funded, the deal cannot simply be
        cancelled — staff must dispute it, which is what makes the refund a
        recorded decision rather than a quiet reversal."""
        from app.models.enums import DealStatus  # noqa: PLC0415
        from app.services.deal_service import VALID_TRANSITIONS  # noqa: PLC0415

        for frm in (DealStatus.paid_escrow, DealStatus.shipped, DealStatus.delivered):
            assert DealStatus.cancelled not in VALID_TRANSITIONS[frm], (
                f"{frm.value} → cancelled would let a refund skip the dispute"
            )
