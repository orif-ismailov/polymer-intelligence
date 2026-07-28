"""
The lab-order state machine as a table (P6 W2 — T2.2). No database.

The analysis is a manual process (TZ §5): an operator moves every step after
talking to a partner laboratory. So the machine is small, linear, and the only
interesting rules are the ones that stop an operator from lying with it:

  * `done` is not reachable through `transition` at all — it needs the passport,
    and the only door is `complete_with_result`;
  * `rejected` needs a reason (a queue full of unexplained rejections is a queue
    nobody can answer questions about);
  * terminal is terminal.

The table below IS the specification: `_TRANSITIONS` in the service must agree
with it pair for pair, including every pair that must be refused.

Statuses are spelled as strings here, and everything from `app.*` is imported
inside the tests. Importing `app.models.enums` at module scope would pull in the
`app.models` package, which imports every model → `app.core.config` → a
`settings` singleton built from the AMBIENT environment, because the conftest
env patch is a session fixture that has not run at collection time. The symptom
is nine unrelated Telegram-HMAC tests failing, which is a long way from here.
"""

from __future__ import annotations

import pytest

#: from → the statuses reachable from it.
EXPECTED: dict[str, set[str]] = {
    "submitted": {"accepted", "rejected"},
    "accepted": {"sample_awaited", "rejected"},
    "sample_awaited": {"in_analysis", "rejected"},
    "in_analysis": {"done", "rejected"},
    "done": set(),
    "rejected": set(),
}

ALL_STATUSES = list(EXPECTED)


def _lab():  # noqa: ANN202
    from app.services import lab_service  # noqa: PLC0415

    return lab_service


def _status(name: str):  # noqa: ANN202
    from app.models.enums import LabOrderStatus  # noqa: PLC0415

    return LabOrderStatus(name)


class TestTransitionTable:
    def test_the_table_matches_the_specification(self) -> None:
        table = {
            str(frm): {str(t) for t in targets}
            for frm, targets in _lab()._TRANSITIONS.items()
        }
        assert table == EXPECTED

    def test_every_status_has_an_entry(self) -> None:
        """A status missing from the table would KeyError on the first attempt to
        move out of it — in the operator's face, at the worst moment."""
        from app.models.enums import LabOrderStatus  # noqa: PLC0415

        assert set(_lab()._TRANSITIONS) == set(LabOrderStatus)

    @pytest.mark.parametrize(
        ("frm", "to"),
        [(f, t) for f, targets in EXPECTED.items() for t in targets],
    )
    def test_allowed_pairs_are_allowed(self, frm: str, to: str) -> None:
        assert _lab().can_transition(_status(frm), _status(to))

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
        assert not _lab().can_transition(_status(frm), _status(to))

    def test_no_status_loops_back_to_itself(self) -> None:
        for frm, targets in _lab()._TRANSITIONS.items():
            assert frm not in targets

    def test_the_happy_path_is_walkable_end_to_end(self) -> None:
        path = ["submitted", "accepted", "sample_awaited", "in_analysis", "done"]
        for frm, to in zip(path, path[1:], strict=False):
            assert _lab().can_transition(_status(frm), _status(to)), f"{frm} → {to}"

    def test_rejected_is_reachable_from_every_live_status(self) -> None:
        """A lab can turn a job down at any point before it is finished."""
        for name in ("submitted", "accepted", "sample_awaited", "in_analysis"):
            assert _lab().can_transition(_status(name), _status("rejected"))


class TestAvailableTransitions:
    """The dashboard builds its buttons from this, so the UI can never offer a
    move the API would refuse — and never re-implements the machine in TypeScript
    (the rule `escrow_service.available_marks` established)."""

    def test_lists_the_reachable_statuses_in_enum_order(self) -> None:
        assert [
            str(s) for s in _lab().available_transitions(_status("submitted"))
        ] == ["accepted", "rejected"]

    def test_a_finished_order_offers_nothing(self) -> None:
        assert _lab().available_transitions(_status("done")) == []
        assert _lab().available_transitions(_status("rejected")) == []

    def test_done_is_offered_only_from_in_analysis(self) -> None:
        """It is still offered — the dashboard turns it into "upload the result",
        not into a plain status button."""
        done = _status("done")
        assert done in _lab().available_transitions(_status("in_analysis"))
        for name in ("submitted", "accepted", "sample_awaited"):
            assert done not in _lab().available_transitions(_status(name))


class TestReasonAndResultRules:
    def test_rejecting_requires_a_reason(self) -> None:
        assert _status("rejected") in _lab().REASON_REQUIRED

    def test_done_is_not_a_plain_transition(self) -> None:
        """`transition` must refuse it: the result file is what makes an order
        done, and the schema CHECK would reject the row anyway — better a typed
        error than an IntegrityError in the operator's face."""
        assert _status("done") in _lab().RESULT_REQUIRED
