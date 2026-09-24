"""Specifications of a framework contract — «Спецификация № N» (stage 2).

A framework contract (the AKFA 346-01 shape) names no goods and fixes only a
limit; each shipment is a specification — its own goods, prices and payment
terms — signed on its own and invoiced by its own ЭСФ. The form is the real
«Спецификация № 01» to that contract: a table with the price and sum without
VAT, the VAT and the sum with it, the total in words.

How the price is stated is the user's choice (`price_basis`), as on a one-off
contract: WITH VAT keeps the agreed total round, WITHOUT VAT matches the ЭСФ to
the tiyin (see `amounts.vat_line` / `amounts.net_line`).
"""

from __future__ import annotations

import datetime
import decimal
import html
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.domains.contracts import amounts
from app.domains.contracts.terms import _UNIT_LABELS, parse_number, vat_rate_of

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

    from app.domains.accounts.models import UserAccount
    from app.domains.contracts.models import Contract, ContractSpecification

#: The specification's own template (`contract_templates.kind = 'specification'`).
TEMPLATE_CODE = "SPECIFICATION_V1"

#: What a specification may carry beside its lines.
SPEC_KEYS: frozenset[str] = frozenset(
    {"lines", "price_basis", "vat_rate", "payment_mode", "payment_schedule", "delivery_days"}
)

#: Names the specification template may use that the renderer fills.
RENDERED_KEYS: frozenset[str] = frozenset(
    {
        "spec_number", "spec_date", "spec_rows_html", "spec_count", "spec_amount_without_vat",
        "spec_vat_sum", "spec_amount_with_vat", "spec_total_phrase", "contract_number",
        "contract_date",
    }
)

_MAX_LINES = 50


class InvalidSpecification(Exception):
    def __init__(self, fields: list[str]) -> None:
        super().__init__(", ".join(fields))
        self.fields = fields


class NotAFrameworkContract(Exception):
    """Specifications belong to a SIGNED framework contract only."""


class SpecificationNotEditable(Exception):
    """Only a draft specification may be cancelled or changed."""


@dataclass(frozen=True)
class SpecLine:
    ord_no: int
    product: str
    qty: decimal.Decimal
    unit: str
    unit_price: decimal.Decimal
    vat_rate: int | None
    vat: amounts.VatLine


def parse_lines(variables: dict[str, object]) -> list[SpecLine]:
    """The typed lines, validated and split into VAT columns — or every field wrong."""
    raw = variables.get("lines")
    if not isinstance(raw, list) or not raw or len(raw) > _MAX_LINES:
        raise InvalidSpecification(["lines"])
    rate = vat_rate_of(variables.get("vat_rate"))
    net = variables.get("price_basis") == "without_vat"
    errors: list[str] = []
    out: list[SpecLine] = []
    for index, item in enumerate(raw, start=1):
        row = item if isinstance(item, dict) else {}
        product = str(row.get("product") or "").strip()
        qty = parse_number(row.get("qty"))
        price = parse_number(row.get("unit_price"))
        unit = str(row.get("unit") or "").strip()
        row_errors = []
        if not product:
            row_errors.append(f"lines.{index}.product")
        if qty is None or qty <= 0:
            row_errors.append(f"lines.{index}.qty")
        if price is None or price <= 0:
            row_errors.append(f"lines.{index}.unit_price")
        if row_errors or qty is None or price is None:
            errors.extend(row_errors)
            continue
        vat = (
            amounts.net_line(qty=qty, price_without_vat=price, vat_rate=rate)
            if net
            else amounts.vat_line(qty=qty, price_with_vat=price, vat_rate=rate)
        )
        out.append(
            SpecLine(ord_no=index, product=product, qty=qty, unit=unit, unit_price=price,
                     vat_rate=rate, vat=vat)
        )
    if errors:
        raise InvalidSpecification(errors)
    return out


@dataclass(frozen=True)
class Totals:
    amount_without_vat: decimal.Decimal
    vat_sum: decimal.Decimal
    amount_with_vat: decimal.Decimal


def totals(lines: list[SpecLine]) -> Totals:
    zero = decimal.Decimal("0.00")
    return Totals(
        amount_without_vat=sum((line.vat.amount_without_vat for line in lines), zero),
        vat_sum=sum((line.vat.vat_sum for line in lines), zero),
        amount_with_vat=sum((line.vat.amount_with_vat for line in lines), zero),
    )


def render_values(variables: dict[str, object], lines: list[SpecLine]) -> dict[str, str]:
    """What the specification template needs beyond the parties — rows escaped here."""
    rows = []
    for line in lines:
        cells = (
            str(line.ord_no),
            line.product,
            amounts.grouped(line.qty),
            _UNIT_LABELS.get(line.unit, line.unit),
            amounts.grouped(line.vat.price_without_vat),
            amounts.grouped(line.vat.amount_without_vat),
            amounts.grouped(line.vat.vat_sum),
            amounts.grouped(line.vat.amount_with_vat),
        )
        tds = "".join(
            f'<td class="name">{html.escape(c)}</td>' if i == 1 else f"<td>{html.escape(c)}</td>"
            for i, c in enumerate(cells)
        )
        rows.append(f"<tr>{tds}</tr>")
    total = totals(lines)
    return {
        "spec_rows_html": "".join(rows),
        "spec_count": str(len(lines)),
        "spec_amount_without_vat": amounts.grouped(total.amount_without_vat),
        "spec_vat_sum": amounts.grouped(total.vat_sum),
        "spec_amount_with_vat": amounts.grouped(total.amount_with_vat),
        "spec_total_phrase": amounts.sum_phrase(total.amount_with_vat),
    }


# ── the service ───────────────────────────────────────────────────────────────


def is_framework(contract: Contract) -> bool:
    variables = contract.variables if isinstance(contract.variables, dict) else {}
    return variables.get("contract_kind") == "frame"


def list_for(db: Session, contract: Contract) -> list[ContractSpecification]:
    from app.domains.contracts.models import ContractSpecification  # noqa: PLC0415

    return (
        db.query(ContractSpecification)
        .filter(ContractSpecification.contract_id == contract.id)
        .order_by(ContractSpecification.number)
        .all()
    )


def create_specification(
    db: Session,
    contract: Contract,
    account: UserAccount,
    variables: dict[str, object],
    *,
    today: datetime.date,
) -> ContractSpecification:
    """Draw up the next specification of a signed framework contract, render its PDF."""
    from sqlalchemy import func  # noqa: PLC0415

    from app.domains.contracts.models import ContractLine, ContractSpecification  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415

    if contract.status != ContractStatus.active or not is_framework(contract):
        raise NotAFrameworkContract(str(contract.id))
    clean = {k: v for k, v in variables.items() if k in SPEC_KEYS}
    lines = parse_lines(clean)
    total = totals(lines)

    last = (
        db.query(func.max(ContractSpecification.number))
        .filter(ContractSpecification.contract_id == contract.id)
        .scalar()
    )
    spec = ContractSpecification(
        contract_id=contract.id,
        number=int(last or 0) + 1,
        spec_date=today,
        status="draft",
        variables=clean,
        amount_without_vat=total.amount_without_vat,
        vat_sum=total.vat_sum,
        amount_with_vat=total.amount_with_vat,
        created_by_user_account_id=account.id,
    )
    db.add(spec)
    db.flush()

    for line in lines:
        db.add(
            ContractLine(
                contract_id=contract.id,
                specification_id=spec.id,
                ord_no=line.ord_no,
                product_name=line.product,
                qty=line.qty,
                unit=line.unit or None,
                price=line.vat.price_without_vat,
                currency="UZS",
                vat_rate=line.vat_rate,
                amount=line.vat.amount_without_vat,
            )
        )
    db.flush()
    _render_and_store(db, contract, spec, lines)
    return spec


def _render_and_store(
    db: Session, contract: Contract, spec: ContractSpecification, lines: list[SpecLine]
) -> None:
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.contracts import render as contract_render  # noqa: PLC0415
    from app.domains.contracts.models import ContractTemplate  # noqa: PLC0415
    from app.domains.contracts.service import _requisites  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    template = (
        db.query(ContractTemplate)
        .filter(ContractTemplate.code == TEMPLATE_CODE)
        .one()
    )
    body = storage_service.get_object_text(template.body_storage_path)
    contract_vars = contract.variables if isinstance(contract.variables, dict) else {}
    variables: dict[str, object] = {
        "initiator_side": contract_vars.get("initiator_side", "supplier"),
        "contract_number": contract_vars.get("contract_number", ""),
        "contract_date": contract_vars.get("contract_date", ""),
        "spec_number": str(spec.number),
        "spec_date": spec.spec_date.strftime("%d.%m.%Y"),
        **{k: v for k, v in spec.variables.items() if k != "lines"},
        # Last, so nothing typed can stand in for the rows built here.
        **render_values(spec.variables, lines),
    }
    initiator = db.get(Company, contract.initiator_company_id)
    counterparty = db.get(Company, contract.counterparty_company_id)
    if initiator is None or counterparty is None:  # pragma: no cover — FK-guaranteed
        raise NotAFrameworkContract(str(contract.id))
    pdf = contract_render.render_contract_pdf(
        body, variables, _requisites(db, initiator), _requisites(db, counterparty),
        contract_public_id=str(contract.public_id), generated_at="",
    )
    path, sha = storage_service.store_specification_pdf(str(contract.public_id), spec.number, pdf)
    spec.generated_document_path = path
    spec.document_sha256 = sha
    db.flush()


def cancel(db: Session, spec: ContractSpecification) -> None:
    if spec.status != "draft":
        raise SpecificationNotEditable(spec.status)
    spec.status = "cancelled"
    db.flush()
