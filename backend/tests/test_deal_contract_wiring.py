"""The deal↔contract and sample→deal seams (P7.a — W7).

Two links existed in the model and were reachable only from tests:

  * `deal_service.attach_contract` had **no route**, and `ContractCreateIn` had no
    field to carry a `deal_id`, so every contract created through the portal left
    `deals.contract_id` NULL. That is not cosmetic — it breaks the entire chain
    behind it: `CONTRACT_ACTIVATED` looks the deal up BY contract, finds nothing,
    and the deal never reaches `contract_signed`, so escrow is never opened.
  * `deal_service.contract_prefill` had no route either, so "create contract" from
    a deal opened an empty form for two parties who had already agreed a product,
    a quantity and a price.

Plus a third door onto deals — from a sample the buyer has received.
"""

from __future__ import annotations

import pytest


def test_contract_create_accepts_a_deal_id() -> None:
    """The field whose absence orphaned every portal contract from its deal."""
    from app.domains.contracts.schemas import ContractCreateIn

    body = ContractCreateIn(
        initiator_company_id=1, counterparty_company_id=2, template_id=3, deal_id=99
    )
    assert body.deal_id == 99


def test_deal_id_is_optional() -> None:
    """A contract may still be drawn up outside any deal — the offer-sheet path."""
    from app.domains.contracts.schemas import ContractCreateIn

    assert (
        ContractCreateIn(
            initiator_company_id=1, counterparty_company_id=2, template_id=3
        ).deal_id
        is None
    )


def test_the_prefill_route_exists_and_is_company_scoped() -> None:
    from app.domains.deals.api_portal import router

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/companies/{company_id}/deals/{deal_id}/contract-prefill" in paths


def test_the_sample_to_deal_route_exists() -> None:
    from app.domains.lab_orders.api_portal_samples import router

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/samples/{sample_id}/deal" in paths


def test_both_routes_are_mounted() -> None:
    from app.main import create_app

    paths = set(create_app().openapi()["paths"])
    assert "/api/v1/portal/companies/{company_id}/deals/{deal_id}/contract-prefill" in paths
    assert "/api/v1/portal/samples/{sample_id}/deal" in paths


class _Sample:
    def __init__(self, status: object) -> None:
        self.id = 5
        self.status = status
        self.offer_id = 11
        self.buyer_company_id = 1
        self.seller_company_id = 2
        self.deal_id = None


def test_a_sample_that_never_arrived_cannot_become_a_deal() -> None:
    """`received` is the whole precondition: it is the moment the buyer is holding
    the material. Opening from `sent` would let a deal exist for goods still in a
    courier van."""
    from app.domains.deals import service as deal_service
    from app.models.enums import SampleRequestStatus

    with pytest.raises(deal_service.DealRequiresCompany):
        deal_service.open_deal_from_sample(
            object(), _Sample(SampleRequestStatus.sent), object()  # type: ignore[arg-type]
        )


def test_opening_from_a_sample_is_not_wired_to_the_status_change() -> None:
    """Deliberately manual. A received sample says the material arrived, not that
    anyone agreed a price — and `_open` needs an amount. Auto-opening would also
    race the "one live deal per (offer, buyer)" rule and erase the difference
    between "I tested it" and "we agreed to trade".
    """
    from app.services import event_types
    from app.tasks.events import CONSUMERS

    assert CONSUMERS.get(event_types.SAMPLE_REQUEST_STATUS_CHANGED, []) == []
