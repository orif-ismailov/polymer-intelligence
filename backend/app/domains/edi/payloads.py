"""Didox document bodies: «Договор НК» (007) and ЭСФ (002) — P7.a Stage 2, W4.

**Pure.** No session, no settings, no I/O — the caller assembles `PartyRequisites`
and `DocumentLine`s from the database and hands them over. That is what makes the
golden tests worth having: everything that can go wrong with a payload goes wrong
in here, deterministically.

Three properties of this API are not ours to choose:

1. **PascalCase in, all-lowercase out.** We POST `{"ContractDoc": {"ContractNo": …}}`
   and Didox stores and echoes `{"contractdoc": {"contractno": …}}`. The builder
   and the reader are therefore NOT symmetric — `lowercase_keys` exists so the
   read side can be written against what actually comes back.
2. **Extra fields are rejected.** The roaming centre validates the structure
   strictly, so these dicts are built as complete literals rather than assembled
   conditionally — a stray key is a rejected document, not a warning.
3. **Numbers are strings with fixed precision.** `Count` to 6 decimal places,
   every other numeric to 2, dot separator, no digit grouping.

On (3): excess precision RAISES rather than rounding. Real specification sheets do
quote prices at three decimals — 7 686,525 сум/kg is copied from an actual supply
contract — and quietly rounding one would change the total on a document that
reaches the tax authority. Refusing sends the decision back to whoever priced it.
"""

from __future__ import annotations

import datetime
import decimal
from dataclasses import dataclass, field

#: A document body is JSON, and saying so beats `Any`: these payloads are validated
#: field-by-field by a tax authority, so "some object" is exactly the wrong amount
#: of type information to carry around while building one.
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

#: Didox document type codes this module builds.
DOC_TYPE_CONTRACT = "007"
DOC_TYPE_FACTURE = "002"

_MONEY_DP = 2
_COUNT_DP = 6


class PrecisionError(ValueError):
    """A number carries more decimals than Didox accepts for its field."""


class IkpuMissing(ValueError):
    """An offer has no ИКПУ, so it cannot back a Didox document.

    Not an error to work around: back-filling a tax classification for someone
    else's goods is not ours to do, and guessing one puts a wrong code on a
    document that reaches soliq. The seller adds it to their offer, once.
    """

    def __init__(self, offer_id: int | str) -> None:
        super().__init__(f"offer {offer_id} has no ИКПУ")
        self.offer_id = offer_id


def line_from_offer(
    offer: object,
    *,
    ord_no: int,
    name: str,
    count: decimal.Decimal,
    price: decimal.Decimal,
    vat_rate: int | None = 12,
) -> DocumentLine:
    """Build a document line from an offer's cached tax classification.

    The one place the ИКПУ leaves `seller_offers`, so the "no code, no document"
    rule has exactly one enforcement point.
    """
    code = getattr(offer, "ikpu_code", None)
    package = getattr(offer, "ikpu_package_code", None)
    origin = getattr(offer, "ikpu_origin", None)
    if not code or not package or origin is None:
        raise IkpuMissing(getattr(offer, "id", "?"))
    return DocumentLine(
        ord_no=ord_no,
        name=name,
        catalog_code=str(code),
        catalog_name=str(getattr(offer, "ikpu_name", None) or code),
        package_code=str(package),
        package_name=str(getattr(offer, "ikpu_package_name", None) or ""),
        count=count,
        price=price,
        vat_rate=vat_rate,
        origin=int(origin),
    )


@dataclass(frozen=True)
class PartyRequisites:
    """One side of a document, as Didox wants it.

    `fiz_tin`/`fio` are the SIGNING PERSON — their PINFL and full name — not the
    company. We hold them only in `company_person_data`, populated by E-IMZO
    identity confirmation, which is why a company that has never confirmed by
    E-IMZO cannot be a party to a Didox contract.

    `vat_reg_code`/`vat_reg_status` are read PER DOCUMENT from
    `/v1/profile/vatRegStatus` (they are date- and role-sensitive) and are never
    cached on the company row.
    """

    tin: str
    name: str
    address: str | None = None
    oked: str | int | None = None
    account: str | None = None
    bank_mfo: str | None = None
    fiz_tin: str | None = None
    fio: str | None = None
    director: str | None = None
    accountant: str | None = None
    vat_reg_code: str | None = None
    vat_reg_status: int | None = None
    work_phone: str | None = None
    mobile: str | None = None
    branch_code: str = ""
    branch_name: str = ""


@dataclass(frozen=True)
class DocumentLine:
    """One product line, shared by both document types.

    `vat_rate is None` means the line is supplied WITHOUT VAT — which is a
    different statement from a 0% rate and is expressed by a different field
    (`WithoutVat`), so it is modelled as absence rather than as zero.

    `origin` (1 own production · 2 resale · 3 services · 4 not involved) is an ЭСФ
    field; the договор has no equivalent and ignores it.
    """

    ord_no: int
    name: str
    catalog_code: str
    catalog_name: str
    package_code: str
    package_name: str
    count: decimal.Decimal
    price: decimal.Decimal
    vat_rate: int | None = None
    origin: int | None = None
    barcode: str = ""
    #: Kept so `DocumentLine(**{**line.__dict__, …})` stays a faithful copy.
    _reserved: tuple[()] = field(default=(), repr=False)


# ── numeric formatting ────────────────────────────────────────────────────────


def _fixed(value: decimal.Decimal, places: int, label: str) -> str:
    """Render to exactly `places` decimals, refusing anything finer.

    `normalize()` first so `Decimal("1000.00")` is not mistaken for 2 significant
    decimals when the field allows 6 — the test is about INFORMATION carried, not
    about how the literal was typed.
    """
    exponent = -value.normalize().as_tuple().exponent  # type: ignore[operator]
    if exponent > places:
        raise PrecisionError(
            f"{label}={value} has {exponent} decimal places; Didox allows {places}"
        )
    quantized = value.quantize(decimal.Decimal(1).scaleb(-places))
    # `:f` and never `str()`: `str(Decimal("1000").normalize())` is `"1E+3"`, and
    # scientific notation in a quantity field on a document bound for the tax
    # authority is not a formatting preference.
    text = f"{quantized:f}"
    if places == _COUNT_DP and "." in text:
        # Count is written as short as it carries — `1000`, not `1000.000000`,
        # matching what the live contour echoed back for a whole quantity.
        text = text.rstrip("0").rstrip(".")
    return text


def _money(value: decimal.Decimal, label: str) -> str:
    return _fixed(value, _MONEY_DP, label)


def _count(value: decimal.Decimal, label: str = "Count") -> str:
    return _fixed(value, _COUNT_DP, label)


def _day(value: datetime.date) -> str:
    """`yyyy-MM-dd`, no time and no zone — the only date format accepted."""
    return value.strftime("%Y-%m-%d")


@dataclass(frozen=True)
class _LineTotals:
    delivery_sum: decimal.Decimal
    vat_sum: decimal.Decimal
    with_vat: decimal.Decimal


def _totals(line: DocumentLine) -> _LineTotals:
    """Compute the three derived sums rather than trusting a caller's arithmetic.

    A line whose `DeliverySum` disagrees with `Count × Summa` is accepted by Didox
    and then disputed by an accountant, so there is no version of this the caller
    should be allowed to supply.
    """
    delivery = (line.count * line.price).quantize(
        decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP
    )
    vat = decimal.Decimal("0.00")
    if line.vat_rate is not None:
        vat = (delivery * decimal.Decimal(line.vat_rate) / decimal.Decimal(100)).quantize(
            decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP
        )
    return _LineTotals(delivery_sum=delivery, vat_sum=vat, with_vat=delivery + vat)


def _has_vat(lines: list[DocumentLine]) -> bool:
    return any(line.vat_rate is not None for line in lines)


# ── 007 «Договор НК» ──────────────────────────────────────────────────────────


def _party_007(party: PartyRequisites) -> JsonObject:
    return {
        "Tin": party.tin,
        "Name": party.name,
        "BranchCode": party.branch_code,
        "BranchName": party.branch_name,
        "FizTin": party.fiz_tin or "",
        "Fio": party.fio or "",
        "Address": party.address or "",
        "WorkPhone": party.work_phone or "",
        "Mobile": party.mobile or "",
        "Oked": party.oked or "",
        "Account": party.account or "",
        "BankId": party.bank_mfo or "",
    }


def _product_007(line: DocumentLine) -> JsonObject:
    totals = _totals(line)
    return {
        "OrdNo": line.ord_no,
        "Name": line.name,
        "CatalogCode": line.catalog_code,
        "CatalogName": line.catalog_name,
        "Barcode": line.barcode,
        # Always null: the package is identified by PackageCode, and MeasureId is
        # one of the fields the roaming rules name as forbidden on an ЭСФ. Sending
        # a value here on one type and not the other invites the wrong habit.
        "MeasureId": None,
        "PackageCode": line.package_code,
        "PackageName": line.package_name,
        "Count": _count(line.count),
        "Summa": _money(line.price, "Summa"),
        "DeliverySum": _money(totals.delivery_sum, "DeliverySum"),
        "VatRate": str(line.vat_rate) if line.vat_rate is not None else "0",
        "VatSum": _money(totals.vat_sum, "VatSum"),
        "DeliverySumWithVat": _money(totals.with_vat, "DeliverySumWithVat"),
        "WithoutVat": line.vat_rate is None,
    }


def build_contract_007(
    *,
    number: str,
    date: datetime.date,
    expires_on: datetime.date,
    place: str,
    title: str,
    seller: PartyRequisites,
    buyer: PartyRequisites,
    lines: list[DocumentLine],
    parts: list[tuple[str, str]],
) -> JsonObject:
    """The legally significant contract body — it reaches my.soliq.uz via roaming.

    `parts` is the contract's prose, section by section: `(title, body)` pairs
    rendered from our own template. Note its keys are lowercase in the REQUEST
    too — the one block Didox spells that way going in, not just coming back.
    """
    return {
        "ContractDoc": {
            "ContractName": title,
            "ContractNo": number,
            "ContractDate": _day(date),
            "ContractExpireDate": _day(expires_on),
            "ContractPlace": place,
        },
        "Owner": _party_007(seller),
        "Clients": [_party_007(buyer)],
        "Parts": [
            {"ordno": i, "title": t, "body": b} for i, (t, b) in enumerate(parts, start=1)
        ],
        "Products": [_product_007(line) for line in lines],
        "HasVat": _has_vat(lines),
    }


# ── 002 ЭСФ (счёт-фактура) ────────────────────────────────────────────────────


def _party_002(party: PartyRequisites) -> JsonObject:
    return {
        "Name": party.name,
        "BranchCode": party.branch_code,
        "BranchName": party.branch_name,
        "VatRegCode": party.vat_reg_code or "",
        "Account": party.account or "",
        "BankId": party.bank_mfo or "",
        "Address": party.address or "",
        # Mandatory on BOTH sides — the docs say so twice.
        "Director": party.director or "",
        "Accountant": party.accountant or "",
        "VatRegStatus": party.vat_reg_status,
    }


def _product_002(line: DocumentLine, *, has_vat: bool) -> JsonObject:
    totals = _totals(line)
    product: JsonObject = {
        "OrdNo": line.ord_no,
        "LgotaId": None,
        "CommittentName": "",
        "CommittentTin": "",
        "CommittentVatRegCode": "",
        "CommittentVatRegStatus": None,
        "Name": line.name,
        "CatalogCode": line.catalog_code,
        "CatalogName": line.catalog_name,
        "Marks": None,
        "Barcode": line.barcode,
        "PackageCode": line.package_code,
        "PackageName": line.package_name,
        "Count": _count(line.count),
        "Summa": _money(line.price, "Summa"),
        "DeliverySum": _money(totals.delivery_sum, "DeliverySum"),
        "VatRate": str(line.vat_rate) if line.vat_rate is not None else "0",
        "VatSum": _money(totals.vat_sum, "VatSum"),
        "ExciseRate": 0,
        "ExciseSum": 0,
        "DeliverySumWithVat": _money(totals.with_vat, "DeliverySumWithVat"),
        "LgotaType": None,
        "LgotaName": None,
        "LgotaVatSum": None,
        "WarehouseId": None,
        "Origin": line.origin,
    }
    # "WithoutVat передаётся только когда ProductList.HasVat = true" — on a
    # VAT-free invoice the key is ABSENT, not `false`.
    if has_vat:
        product["WithoutVat"] = line.vat_rate is None
    return product


def build_facture_002(
    *,
    number: str,
    date: datetime.date,
    contract_number: str,
    contract_date: datetime.date,
    seller: PartyRequisites,
    buyer: PartyRequisites | None,
    lines: list[DocumentLine],
    factura_type: int = 0,
    didox_contract_id: str | None = None,
    single_sided_type: int | None = None,
) -> JsonObject:
    """The счёт-фактура — what actually appears in both parties' soliq ЭСФ registry.

    `contract_number`/`contract_date` must match the договор EXACTLY; they are read
    off the stored 007 row and never recomputed, because a mismatched pair is
    refused by the roaming centre.

    `didox_contract_id` is Didox's own hex id for the договор (the `contractid`
    from its create response, NOT the `_id`). It rides as a service field, outside
    the roaming-validated body.
    """
    has_vat = _has_vat(lines)
    body: JsonObject = {
        "Version": 1,
        "WaybillLocalIds": [],
        "HasMarking": False,
        "HasRent": False,
        "FacturaRentDoc": None,
        "FacturaType": factura_type,
        "ProductList": {
            "HasCommittent": False,
            "HasLgota": False,
            "Tin": seller.tin,
            "HideReportCommittent": False,
            "HasExcise": False,
            "HasVat": has_vat,
            "Products": [_product_002(line, has_vat=has_vat) for line in lines],
        },
        "FacturaDoc": {"FacturaNo": number, "FacturaDate": _day(date)},
        "ContractDoc": {"ContractNo": contract_number, "ContractDate": _day(contract_date)},
        # The my.soliq.uz-registered contract id — a DIFFERENT namespace from
        # Didox's own ids, and one we do not have unless the contract was
        # registered there. Null is correct until then.
        "ContractId": None,
        "LotId": "",
        "OldFacturaDoc": None,
        "SellerTin": seller.tin,
        "Seller": _party_002(seller),
        "ItemReleasedDoc": None,
        "BuyerTin": buyer.tin if buyer else "",
        "Buyer": _party_002(buyer) if buyer else None,
        "FacturaInvestmentObjectDoc": None,
        "FacturaEmpowermentDoc": None,
        "ForeignCompany": None,
    }
    if single_sided_type is not None:
        body["SingleSidedType"] = single_sided_type
    if didox_contract_id:
        body["didoxcontractid"] = didox_contract_id
    return body


# ── the read side ─────────────────────────────────────────────────────────────


def lowercase_keys(value: JsonValue) -> JsonValue:
    """Recursively lowercase every mapping key, leaving values untouched.

    Didox stores `document_json` with every key lowercased, so code that reads a
    document back cannot reuse the PascalCase names it sent. Applying this to our
    own payload gives a test the exact shape the provider will echo, which is how
    the asymmetry stays visible instead of being rediscovered per document type.
    """
    if isinstance(value, dict):
        return {str(k).lower(): lowercase_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [lowercase_keys(v) for v in value]
    return value
