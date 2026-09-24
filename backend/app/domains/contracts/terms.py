"""A contract's commercial terms, read out of `variables` as data.

`variables` is what the document is rendered from: strings, typed by a person —
«1 150,50», «20», «договорная». Two readers need them as numbers: the Didox line
(`edi/contract_docs.contract_line_terms`) and the structured copy kept for market
analytics (`sync_structured`). One parse, so the two can never read the same
contract differently.
"""

from __future__ import annotations

import decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

    from app.domains.contracts.models import Contract

_CENT = decimal.Decimal("0.01")


def parse_number(raw: object) -> decimal.Decimal | None:
    """`«1 150,50»` → `1150.50`; anything that is not a finite number → None."""
    text = str(raw or "").replace(",", ".").replace(" ", "").replace(" ", "")
    if not text:
        return None
    try:
        value = decimal.Decimal(text)
    except decimal.InvalidOperation:
        return None
    return value if value.is_finite() else None


def _text(raw: object) -> str | None:
    value = str(raw or "").strip()
    return value or None


def _variables(contract: Contract) -> dict[str, object]:
    return contract.variables if isinstance(contract.variables, dict) else {}


def line_name(contract: Contract) -> str:
    return _text(_variables(contract).get("product")) or contract.title


def sync_structured(db: Session, contract: Contract) -> None:
    """Write the terms onto the contract's columns and its one `contract_lines` row.

    Called on every create and edit. A number that does not parse is stored as
    NULL — a zero would be a price nobody agreed to, and it would drag every
    average it was counted in.
    """
    from app.domains.contracts.models import ContractLine  # noqa: PLC0415

    variables = _variables(contract)
    qty = parse_number(variables.get("qty"))
    price = parse_number(variables.get("price"))
    amount = (qty * price).quantize(_CENT) if qty is not None and price is not None else None
    currency = _text(variables.get("currency"))

    contract.currency = currency
    contract.incoterms = _text(variables.get("incoterms"))
    contract.payment_terms = _text(variables.get("payment_terms"))
    contract.delivery_window = _text(variables.get("delivery_window"))
    contract.amount_total = amount

    line = (
        db.query(ContractLine)
        .filter(ContractLine.contract_id == contract.id, ContractLine.ord_no == 1)
        .one_or_none()
    )
    if line is None:
        line = ContractLine(contract_id=contract.id, ord_no=1)
        db.add(line)
    line.product_name = line_name(contract)
    line.qty = qty
    line.unit = _text(variables.get("unit"))
    line.price = price
    line.currency = currency
    line.amount = amount
    db.flush()


def stamp_classification(
    db: Session,
    contract_id: int,
    *,
    ord_no: int,
    ikpu_code: str,
    ikpu_name: str,
    package_code: str,
    package_name: str,
    vat_rate: int | None,
) -> None:
    """Record the tax classification a Didox document gave a contract line.

    It is first known when the document is built — from the offer, or picked on
    the card for a tender contract — so it is written back then.
    """
    from app.domains.contracts.models import ContractLine  # noqa: PLC0415

    line = (
        db.query(ContractLine)
        .filter(ContractLine.contract_id == contract_id, ContractLine.ord_no == ord_no)
        .one_or_none()
    )
    if line is None:
        return
    line.ikpu_code = ikpu_code
    line.ikpu_name = ikpu_name
    line.package_code = package_code
    line.package_name = package_name
    line.vat_rate = vat_rate
    db.flush()
