"""A contract's commercial terms, read out of `variables` as data.

`variables` is what the document is rendered from: strings, typed by a person —
«1 150,50», «20», «договорная». Two readers need them as numbers: the Didox line
(`edi/contract_docs.contract_line_terms`) and the structured copy kept for market
analytics (`sync_structured`). One parse, so the two can never read the same
contract differently.
"""

from __future__ import annotations

import datetime
import decimal
from typing import TYPE_CHECKING

from app.domains.contracts import amounts

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


#: Values the renderer computes from the typed ones — a template may use them, no
#: form asks for them. `templates.renderable_names` reads this.
DERIVED_KEYS: frozenset[str] = frozenset(
    {
        "spec_qty",
        "spec_unit",
        "spec_unit_price",
        "spec_price_without_vat",
        "spec_amount_without_vat",
        "spec_vat_sum",
        "spec_amount_with_vat",
        "spec_total_phrase",
        "amount_total_phrase",
    }
)


_UNIT_LABELS = {"kg": "кг", "t": "т", "pcs": "шт"}


def vat_rate_of(raw: object) -> int | None:
    """`"12"` → 12, `"none"`/blank → None («без НДС»). Anything else → 12."""
    text = str(raw or "").strip().lower()
    if text in {"none", "без ндс"}:
        return None
    if text == "":
        return 12
    try:
        return int(text)
    except ValueError:
        return 12


def spec_line(variables: dict[str, object]) -> amounts.VatLine | None:
    """The one line of a contract, split into VAT columns — or None if it does not parse.

    `price_basis` is the user's choice, not ours (24.09.2026): a price WITH VAT
    keeps the agreed total round, as the real MGBUS specifications do, and may
    then differ from its ЭСФ by a few soum; a price WITHOUT VAT matches the ЭСФ
    to the tiyin.
    """
    qty = parse_number(variables.get("qty"))
    price = parse_number(variables.get("unit_price"))
    if qty is None or price is None or qty <= 0:
        return None
    rate = vat_rate_of(variables.get("vat_rate"))
    if variables.get("price_basis") == "without_vat":
        return amounts.net_line(qty=qty, price_without_vat=price, vat_rate=rate)
    return amounts.vat_line(qty=qty, price_with_vat=price, vat_rate=rate)


def derived_values(variables: dict[str, object]) -> dict[str, str]:
    """Totals and the sum in words, computed — never typed, so they cannot disagree."""
    out: dict[str, str] = {}
    line = spec_line(variables)
    if line is not None:
        qty = parse_number(variables.get("qty"))
        price = parse_number(variables.get("unit_price"))
        out.update(
            spec_qty=amounts.grouped(qty) if qty is not None else "",
            spec_unit=_UNIT_LABELS.get(str(variables.get("unit") or ""), str(variables.get("unit") or "")),
            spec_unit_price=amounts.grouped(price) if price is not None else "",
            spec_price_without_vat=amounts.grouped(line.price_without_vat),
            spec_amount_without_vat=amounts.grouped(line.amount_without_vat),
            spec_vat_sum=amounts.grouped(line.vat_sum),
            spec_amount_with_vat=amounts.grouped(line.amount_with_vat),
            spec_total_phrase=amounts.sum_phrase(line.amount_with_vat),
        )
    if variables.get("contract_kind") == "frame":
        limit = parse_number(variables.get("amount_limit"))
        if limit is not None:
            out["amount_total_phrase"] = amounts.sum_phrase(limit)
    elif line is not None:
        out["amount_total_phrase"] = amounts.sum_phrase(line.amount_with_vat)
    return out


def typed_date(raw: object) -> datetime.date | None:
    """«15.01.2026» or «2026-01-15» as the parties typed it; anything else → None."""
    text = str(raw or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date()  # noqa: DTZ007 — a calendar date
        except ValueError:
            continue
    return None


def _text(raw: object) -> str | None:
    value = str(raw or "").strip()
    return value or None


def _variables(contract: Contract) -> dict[str, object]:
    return contract.variables if isinstance(contract.variables, dict) else {}


def line_name(contract: Contract) -> str:
    return _text(_variables(contract).get("product")) or contract.title


def sync_structured(db: Session, contract: Contract) -> None:
    """Write the terms onto the contract's columns and its `contract_lines` row.

    Called on every create and edit. A number that does not parse is stored as
    NULL — a zero would be a price nobody agreed to, and it would drag every
    average it was counted in.

    Two shapes of contract. The MGBUS-based templates price a line WITH VAT in
    soum (`unit_price`, with or without VAT as `price_basis` says); the stored unit price is the price WITHOUT it — what
    analytics compares — and the contract total is what the parties signed. A
    framework contract has no goods of its own: its total is the limit, and its
    lines arrive with the specifications.
    """
    from app.domains.contracts.models import ContractLine  # noqa: PLC0415

    variables = _variables(contract)
    existing = (
        db.query(ContractLine)
        .filter(
            ContractLine.contract_id == contract.id,
            ContractLine.specification_id.is_(None),
            ContractLine.ord_no == 1,
        )
        .one_or_none()
    )

    if "contract_kind" in variables:
        contract.currency = "UZS"
        contract.incoterms = _text(variables.get("delivery_basis"))
        contract.payment_terms = _text(variables.get("payment_mode"))
        contract.delivery_window = _text(variables.get("delivery_days"))
        if variables.get("contract_kind") == "frame":
            limit = parse_number(variables.get("amount_limit"))
            contract.amount_total = limit.quantize(_CENT) if limit is not None else None
            if existing is not None:
                db.delete(existing)
            db.flush()
            return
        vat = spec_line(variables)
        line = existing or ContractLine(contract_id=contract.id, ord_no=1)
        if existing is None:
            db.add(line)
        line.product_name = line_name(contract)
        line.qty = parse_number(variables.get("qty"))
        line.unit = _text(variables.get("unit"))
        line.price = vat.price_without_vat if vat is not None else None
        line.currency = "UZS"
        line.vat_rate = vat_rate_of(variables.get("vat_rate"))
        line.amount = vat.amount_without_vat if vat is not None else None
        contract.amount_total = vat.amount_with_vat if vat is not None else None
        db.flush()
        return

    qty = parse_number(variables.get("qty"))
    price = parse_number(variables.get("price"))
    amount = (qty * price).quantize(_CENT) if qty is not None and price is not None else None
    currency = _text(variables.get("currency"))

    contract.currency = currency
    contract.incoterms = _text(variables.get("incoterms"))
    contract.payment_terms = _text(variables.get("payment_terms"))
    contract.delivery_window = _text(variables.get("delivery_window"))
    contract.amount_total = amount

    line = existing or ContractLine(contract_id=contract.id, ord_no=1)
    if existing is None:
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
        .filter(
            ContractLine.contract_id == contract_id,
            ContractLine.specification_id.is_(None),
            ContractLine.ord_no == ord_no,
        )
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
