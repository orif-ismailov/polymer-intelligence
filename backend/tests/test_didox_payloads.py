"""Didox document payloads — «Договор НК» 007 and ЭСФ 002 (P7.a Stage 2 — W4).

These builders are pure, and this is the file that has to be right: a payload the
roaming centre rejects fails at SEND time, after the user has already loaded a key
and typed its password, and a payload it ACCEPTS with wrong numbers is a false
statement to the tax authority.

The 007 golden is shaped against a body `testapi3` really accepted on 2026-08-19
(seller OOO KRAEMER INC / 590640341, buyer OOO KOUTS INC / 520879516), not against
the documentation. The roaming rules asserted here come from
`reference/07-document-json.md` §1 and are each tested on their own, because they
fail independently:

  * no extra fields — asserted as key-set EQUALITY, since "лишние поля запрещены"
    is not a subset rule;
  * `Count` ≤6 dp, every other numeric ≤2 dp, dot separator, no grouping;
  * unused objects are `null`, never `{}` with empty strings;
  * dates strictly `yyyy-MM-dd`;
  * `Director` present on both sides;
  * `WithoutVat` present **iff** `HasVat` is true.
"""

from __future__ import annotations

import datetime
import decimal
from typing import Any

import pytest

from app.domains.edi.payloads import (
    DocumentLine,
    PartyRequisites,
    PrecisionError,
    build_contract_007,
    build_facture_002,
    lowercase_keys,
)

D = decimal.Decimal

SELLER = PartyRequisites(
    tin="590640341",
    name="OOO KRAEMER INC",
    address="Тошкент",
    oked="46900",
    account="20208000900000000001",
    bank_mfo="00401",
    fiz_tin="31112553768740",
    fio="LEIGHA HARRISON JERMAN",
    director="LEIGHA HARRISON JERMAN",
    accountant="LEIGHA HARRISON JERMAN",
    vat_reg_code="326080220838",
    vat_reg_status=20,
    work_phone="998902233939",
    mobile="998902233939",
)

BUYER = PartyRequisites(
    tin="520879516",
    name="OOO KOUTS INC",
    address="Тошкент",
    oked="46900",
    account="20208000400308125001",
    bank_mfo="00974",
    fiz_tin="33932263787236",
    fio="VINITA PALMER TEDIE",
    director="VINITA PALMER TEDIE",
    accountant="VINITA PALMER TEDIE",
    vat_reg_code="326040002521",
    vat_reg_status=20,
    work_phone="998913489575",
    mobile="998913489575",
)

#: 1 tonne of LLDPE — the user's own worked example.
LINE = DocumentLine(
    ord_no=1,
    name="Полиэтилен линейный в гранулах LL 0209AA",
    catalog_code="02201001001000000",
    catalog_name="Полиэтилен",
    package_code="1505731",
    package_name="кг",
    count=D("1000"),
    price=D("14553.57"),
    vat_rate=12,
    origin=1,
)

PARTS = [("Предмет договора", "Поставка полиэтилена в гранулах.")]


def _contract(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": "PI-2026-000001",
        "date": datetime.date(2026, 8, 19),
        "expires_on": datetime.date(2026, 12, 31),
        "place": "Тошкент",
        "title": "Поставка полимеров",
        "seller": SELLER,
        "buyer": BUYER,
        "lines": [LINE],
        "parts": PARTS,
    }
    base.update(kw)
    return build_contract_007(**base)


def _facture(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": "ЭСФ-2026-000001",
        "date": datetime.date(2026, 8, 19),
        "contract_number": "PI-2026-000001",
        "contract_date": datetime.date(2026, 8, 19),
        "seller": SELLER,
        "buyer": BUYER,
        "lines": [LINE],
    }
    base.update(kw)
    return build_facture_002(**base)


# ── 007 Договор НК ────────────────────────────────────────────────────────────


class TestContract007:
    def test_top_level_key_set_is_exact(self) -> None:
        """Extra fields are forbidden outright, so this is equality, not `>=`."""
        assert set(_contract()) == {
            "ContractDoc",
            "Owner",
            "Clients",
            "Parts",
            "Products",
            "HasVat",
        }

    def test_owner_and_client_carry_the_signer_identity(self) -> None:
        """`FizTin`/`Fio` are the SIGNING PERSON, not the company.

        We hold them only in `company_person_data`, filled by E-IMZO confirmation —
        which is why a Didox contract requires an E-IMZO-confirmed company.
        """
        doc = _contract()
        assert doc["Owner"]["FizTin"] == "31112553768740"
        assert doc["Owner"]["Fio"] == "LEIGHA HARRISON JERMAN"
        assert doc["Clients"][0]["FizTin"] == "33932263787236"

    def test_party_key_sets_are_exact(self) -> None:
        expected = {
            "Tin", "Name", "BranchCode", "BranchName", "FizTin", "Fio",
            "Address", "WorkPhone", "Mobile", "Oked", "Account", "BankId",
        }
        doc = _contract()
        assert set(doc["Owner"]) == expected
        assert set(doc["Clients"][0]) == expected

    def test_product_key_set_is_exact(self) -> None:
        assert set(_contract()["Products"][0]) == {
            "OrdNo", "Name", "CatalogCode", "CatalogName", "Barcode", "MeasureId",
            "PackageCode", "PackageName", "Count", "Summa", "DeliverySum",
            "VatRate", "VatSum", "DeliverySumWithVat", "WithoutVat",
        }

    def test_totals_are_computed_not_taken_on_trust(self) -> None:
        """1000 × 14 553.57 = 14 553 570.00, VAT 12% = 1 746 428.40."""
        product = _contract()["Products"][0]
        assert product["Count"] == "1000"
        assert product["Summa"] == "14553.57"
        assert product["DeliverySum"] == "14553570.00"
        assert product["VatSum"] == "1746428.40"
        assert product["DeliverySumWithVat"] == "16299998.40"
        assert _contract()["HasVat"] is True

    def test_parts_are_numbered_and_lowercase_keyed(self) -> None:
        """`Parts` is the one block Didox spells in lowercase in the REQUEST too."""
        assert _contract()["Parts"] == [
            {"ordno": 1, "title": "Предмет договора", "body": "Поставка полиэтилена в гранулах."}
        ]

    def test_dates_are_plain_iso_days(self) -> None:
        doc = _contract()["ContractDoc"]
        assert doc["ContractDate"] == "2026-08-19"
        assert doc["ContractExpireDate"] == "2026-12-31"

    def test_a_vat_free_line_sets_hasvat_false(self) -> None:
        free = DocumentLine(**{**LINE.__dict__, "vat_rate": None})
        doc = _contract(lines=[free])
        assert doc["HasVat"] is False
        assert doc["Products"][0]["WithoutVat"] is True
        assert doc["Products"][0]["VatSum"] == "0.00"


# ── 002 ЭСФ ───────────────────────────────────────────────────────────────────


class TestFacture002:
    def test_top_level_key_set_is_exact(self) -> None:
        assert set(_facture()) == {
            "Version", "WaybillLocalIds", "HasMarking", "HasRent", "FacturaRentDoc",
            "FacturaType", "ProductList", "FacturaDoc", "ContractDoc", "ContractId",
            "LotId", "OldFacturaDoc", "SellerTin", "Seller", "ItemReleasedDoc",
            "BuyerTin", "Buyer", "FacturaInvestmentObjectDoc", "FacturaEmpowermentDoc",
            "ForeignCompany",
        }

    def test_unused_objects_are_null_not_empty_objects(self) -> None:
        """`{}` with empty strings is explicitly rejected by the roaming centre."""
        doc = _facture()
        for field in (
            "FacturaRentDoc", "OldFacturaDoc", "ItemReleasedDoc",
            "FacturaInvestmentObjectDoc", "FacturaEmpowermentDoc", "ForeignCompany",
        ):
            assert doc[field] is None, field

    def test_both_parties_carry_a_director(self) -> None:
        """Mandatory on both sides — the one field the docs call out twice."""
        doc = _facture()
        assert doc["Seller"]["Director"] == "LEIGHA HARRISON JERMAN"
        assert doc["Buyer"]["Director"] == "VINITA PALMER TEDIE"

    def test_vat_registration_is_carried_per_party(self) -> None:
        doc = _facture()
        assert doc["Seller"]["VatRegCode"] == "326080220838"
        assert doc["Seller"]["VatRegStatus"] == 20
        assert doc["Buyer"]["VatRegCode"] == "326040002521"

    def test_origin_rides_on_every_product(self) -> None:
        assert _facture()["ProductList"]["Products"][0]["Origin"] == 1

    def test_without_vat_is_sent_only_when_hasvat(self) -> None:
        """"`WithoutVat` передаётся только когда HasVat = true" — so on a VAT-free
        invoice the key must be ABSENT, not `false`."""
        assert "WithoutVat" in _facture()["ProductList"]["Products"][0]

        free = DocumentLine(**{**LINE.__dict__, "vat_rate": None})
        doc = _facture(lines=[free])
        assert doc["ProductList"]["HasVat"] is False
        assert "WithoutVat" not in doc["ProductList"]["Products"][0]

    def test_contract_reference_is_copied_verbatim(self) -> None:
        """The ЭСФ's ContractNo must equal the договор's number exactly, or the
        roaming centre refuses the pair."""
        doc = _facture()
        assert doc["ContractDoc"] == {"ContractNo": "PI-2026-000001", "ContractDate": "2026-08-19"}

    def test_didox_contract_id_is_a_service_field_outside_the_body(self) -> None:
        """`didoxcontractid` links the ЭСФ to its договор. It is Didox's own
        plumbing and is NOT one of the roaming-validated fields, so it only
        appears when we actually have an id."""
        assert "didoxcontractid" not in _facture()
        linked = _facture(didox_contract_id="6a857e3f7a20272c0c01f12c")
        assert linked["didoxcontractid"] == "6a857e3f7a20272c0c01f12c"

    def test_single_sided_drops_the_buyer(self) -> None:
        doc = _facture(buyer=None, single_sided_type=1)
        assert doc["Buyer"] is None
        assert doc["BuyerTin"] == ""
        assert doc["SingleSidedType"] == 1


# ── numeric precision ─────────────────────────────────────────────────────────


class TestPrecision:
    def test_count_allows_six_decimals(self) -> None:
        line = DocumentLine(**{**LINE.__dict__, "count": D("0.123456")})
        assert _contract(lines=[line])["Products"][0]["Count"] == "0.123456"

    def test_seven_decimals_in_count_is_rejected(self) -> None:
        line = DocumentLine(**{**LINE.__dict__, "count": D("0.1234567")})
        with pytest.raises(PrecisionError):
            _contract(lines=[line])

    def test_three_decimals_in_money_is_rejected_not_rounded(self) -> None:
        """Real spec sheets really do quote prices at 3 dp (7 686,525 сум/kg is
        from an actual MGBUS contract), and Didox allows 2. Rounding it here would
        silently change the total on a legally significant document — so it raises
        and the caller decides."""
        line = DocumentLine(**{**LINE.__dict__, "price": D("7686.525")})
        with pytest.raises(PrecisionError):
            _contract(lines=[line])

    def test_money_is_dot_separated_with_no_grouping(self) -> None:
        line = DocumentLine(**{**LINE.__dict__, "count": D("1000000"), "price": D("1234.5")})
        product = _contract(lines=[line])["Products"][0]
        assert product["DeliverySum"] == "1234500000.00"
        assert "," not in product["DeliverySum"]
        assert " " not in product["DeliverySum"]

    def test_money_is_always_two_decimals_even_when_whole(self) -> None:
        line = DocumentLine(**{**LINE.__dict__, "count": D("2"), "price": D("100")})
        assert _contract(lines=[line])["Products"][0]["Summa"] == "100.00"


# ── the read side ─────────────────────────────────────────────────────────────


class TestLowercaseRoundTrip:
    def test_every_key_comes_back_lowercased(self) -> None:
        """PascalCase in, all-lowercase out — confirmed live. The serializer and
        the parser are NOT symmetric, which is the trap this pins."""
        doc = _contract()
        echoed = lowercase_keys(doc)
        assert "ContractDoc" not in echoed
        assert echoed["contractdoc"]["contractno"] == "PI-2026-000001"
        assert echoed["owner"]["fiztin"] == "31112553768740"
        assert echoed["products"][0]["deliverysumwithvat"] == "16299998.40"

    def test_lowercasing_recurses_through_lists_and_leaves_values_alone(self) -> None:
        out = lowercase_keys({"A": [{"B": "KeepMe"}], "C": {"D": {"E": 1}}})
        assert out == {"a": [{"b": "KeepMe"}], "c": {"d": {"e": 1}}}
