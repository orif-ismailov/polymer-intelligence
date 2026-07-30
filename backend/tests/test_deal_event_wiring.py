"""
Outbox wiring for the deals context (P2 W1 — T1.4). No database needed.

The deal reacts to contract events instead of the contracts context writing to
deals tables. That only works if the consumers are actually registered and the
task module is actually loaded by the worker — two things that fail silently:
an unregistered consumer makes the event "acknowledged, no side effects", and a
task module missing from `_TASK_MODULES` raises "unregistered task" at dispatch.
"""

from __future__ import annotations


class TestConsumerRegistration:
    def test_contract_events_reach_the_deals_consumers(self) -> None:
        import app.tasks.deals as deal_tasks  # noqa: PLC0415
        from app.services import event_types  # noqa: PLC0415
        from app.tasks.events import CONSUMERS  # noqa: PLC0415

        assert deal_tasks.advance_deal_on_contract_sent in CONSUMERS[event_types.CONTRACT_SENT]
        assert (
            deal_tasks.advance_deal_on_contract_activated
            in CONSUMERS[event_types.CONTRACT_ACTIVATED]
        )
        for event_type in (event_types.CONTRACT_DECLINED, event_types.CONTRACT_CANCELLED):
            assert deal_tasks.roll_back_deal_on_contract_closed in CONSUMERS[event_type], (
                f"{event_type} must release the deal from contract_pending"
            )

    def test_registration_is_idempotent(self) -> None:
        """Task modules get imported more than once across processes; a second
        import must not queue the same consumer twice (double transitions)."""
        import app.tasks.deals as deal_tasks  # noqa: PLC0415
        from app.services import event_types  # noqa: PLC0415
        from app.tasks.events import CONSUMERS  # noqa: PLC0415

        deal_tasks._register_consumers()
        deal_tasks._register_consumers()
        assert (
            CONSUMERS[event_types.CONTRACT_ACTIVATED].count(
                deal_tasks.advance_deal_on_contract_activated
            )
            == 1
        )

    def test_deal_events_are_known_to_the_dispatcher(self) -> None:
        """An event type absent from ALL_EVENT_TYPES is logged unroutable and
        dropped — the deal notifications in W3 would never fire."""
        from app.services import event_types  # noqa: PLC0415

        for name in (
            "DEAL_OPENED",
            "DEAL_STATUS_CHANGED",
            "DEAL_MESSAGE_POSTED",
            "DEAL_DOCUMENT_ADDED",
            "RFQ_RESPONSE_SUBMITTED",
            "RFQ_RESPONSE_ACCEPTED",
            "RFQ_RESPONSE_NOT_SELECTED",
        ):
            assert getattr(event_types, name) in event_types.ALL_EVENT_TYPES, name


class TestTaskModuleIsLoaded:
    def test_listed_for_the_worker(self) -> None:
        from app.tasks.celery_app import _TASK_MODULES  # noqa: PLC0415

        assert "app.tasks.deals" in _TASK_MODULES, (
            "autodiscover is a no-op here — an unlisted module is an "
            "'unregistered task' at dispatch time"
        )
