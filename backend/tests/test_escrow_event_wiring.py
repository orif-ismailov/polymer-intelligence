"""
Outbox wiring for the payments context (P3 W1 — T1.4).

The escrow is raised by an EVENT, not by whoever happened to sign the contract:
`DEAL_STATUS_CHANGED (to=contract_signed)` → `escrow_service.open_for_deal`.

Two things fail silently here and are asserted rather than assumed: an
unregistered consumer makes the event "acknowledged, no side effects", and a task
module missing from `_TASK_MODULES` raises "unregistered task" at dispatch.

(`app.*` is imported inside the tests: the conftest env patch is a session
fixture and does not exist at collection time.)
"""

from __future__ import annotations


class TestConsumerRegistration:
    def test_a_signed_contract_reaches_the_escrow_consumer(self) -> None:
        import app.tasks.payments as payment_tasks  # noqa: PLC0415
        from app.services import event_types  # noqa: PLC0415
        from app.tasks.events import CONSUMERS  # noqa: PLC0415

        assert (
            payment_tasks.open_escrow_on_deal_signed
            in CONSUMERS[event_types.DEAL_STATUS_CHANGED]
        )

    def test_registration_is_idempotent(self) -> None:
        """Task modules get imported more than once across processes; a second
        import must not queue the same consumer twice (two escrow attempts)."""
        import app.tasks.payments as payment_tasks  # noqa: PLC0415
        from app.services import event_types  # noqa: PLC0415
        from app.tasks.events import CONSUMERS  # noqa: PLC0415

        payment_tasks._register_consumers()
        payment_tasks._register_consumers()
        assert (
            CONSUMERS[event_types.DEAL_STATUS_CHANGED].count(
                payment_tasks.open_escrow_on_deal_signed
            )
            == 1
        )

    def test_it_shares_the_event_with_the_other_consumers(self) -> None:
        """DEAL_STATUS_CHANGED already feeds the staff dispute card. Adding the
        escrow consumer must not displace it — the dispatcher fans out to every
        entry in the list."""
        from app.services import event_types  # noqa: PLC0415
        from app.tasks.events import CONSUMERS  # noqa: PLC0415
        from app.tasks.notify import send_deal_status_to_group  # noqa: PLC0415

        assert send_deal_status_to_group in CONSUMERS[event_types.DEAL_STATUS_CHANGED]


class TestTaskModuleIsLoaded:
    def test_listed_for_the_worker(self) -> None:
        from app.tasks.celery_app import _TASK_MODULES  # noqa: PLC0415

        assert "app.tasks.payments" in _TASK_MODULES, (
            "autodiscover is a no-op here — an unlisted module is an "
            "'unregistered task' at dispatch time"
        )
