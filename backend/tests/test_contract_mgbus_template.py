"""The MGBUS-based supply templates reproduce the real contracts (24.09.2026).

`docs/deals_documents/` holds two real contracts of the same supplier. Rendered
with the switches each of them corresponds to, the template must come out with
the same sections in the same places and the same variant clauses — that is the
whole claim of «a template built on the real contract».
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domains.contracts import render as contract_render
from app.domains.contracts import templates as template_service
from app.seed.seed_contract_templates import _mgbus_schema

_BODY = (
    Path(__file__).resolve().parents[1]
    / "app/seed/data/contract_templates/supply_mgbus_ru.html"
).read_text(encoding="utf-8")

_SUPPLIER = {"legal_name": "СП ООО «MGBUS»", "director": "KULIEV S.", "inn": "306421413"}
_BUYER = {"legal_name": "ООО «AKFA EXTRUSION»", "director": "Юлдашев О. Я.", "inn": "206211534"}

#: Contract 346-01 (AKFA): framework, prepayment, pickup from the warehouse.
_AKFA = {
    "contract_kind": "frame", "contract_number": "346-01", "contract_date": "15 января 2026 г.",
    "initiator_side": "supplier", "supplier_authority": "charter",
    "buyer_authority": "power_of_attorney", "buyer_power_of_attorney": "№ 4 от 05.01.2026",
    "goods_description": "Сырье в ассортименте", "amount_limit": "20000000000",
    "payment_mode": "prepay", "refuse_after_days": "1", "delivery_days": "5",
    "delivery_basis": "supplier_warehouse", "pickup_days": "5",
    "packaging": "none", "quality_section": "no",
    "penalty_delivery_pct": "0,1", "penalty_delivery_cap": "10",
    "penalty_payment_pct": "0,5", "penalty_payment_cap": "50", "refusal_fine_pct": "5",
}

#: Contract 297-08 (GLOBAL PETROCHEMICAL): one-off, payment schedule, bulk, quality.
_GLOBAL = {
    **_AKFA,
    "contract_kind": "one_off", "contract_number": "297-08", "buyer_authority": "charter",
    "product": "МОНОЭТИЛЕНГЛИКОЛЬ МЭГ", "qty": "120000", "unit": "kg",
    "unit_price": "7686.525", "vat_rate": "12",
    "payment_mode": "schedule", "refuse_after_days": "10", "delivery_days": "30",
    "payment_schedule": "22.08.2024 – 25%, 29.08.2024 – 25%, 05.09.2024 – 25%, 12.09.2024 – 25%",
    "delivery_basis": "pickup_address", "delivery_address": "Ташкент, станция «Уртааул»",
    "packaging": "bulk", "quality_section": "yes",
}


def _render(variables: dict[str, str]) -> str:
    return contract_render.render_contract_html(
        _BODY, variables, _SUPPLIER, _BUYER, contract_public_id="x", generated_at="t"
    )


def _sections(html: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S)]


def test_the_akfa_contract_has_its_eight_sections() -> None:
    assert _sections(_render(_AKFA)) == [
        "1. ПРЕДМЕТ ДОГОВОРА",
        "2. УСЛОВИЯ ПОСТАВКИ И РАСЧЕТОВ",
        "3. ОТВЕТСТВЕННОСТЬ СТОРОН",
        "4. СРОК ДЕЙСТВИЯ ДОГОВОРА",
        "5. ПОРЯДОК РАЗРЕШЕНИЯ СПОРОВ",
        "6. ФОРС-МАЖОР",
        "7. ПРОЧИЕ УСЛОВИЯ",
        "8. ЮРИДИЧЕСКИЕ АДРЕСА И РЕКВИЗИТЫ СТОРОН",
    ]


def test_the_akfa_variant_clauses() -> None:
    html = _render(_AKFA)
    assert "1.1. «Поставщик» обязуется поставить, а «Покупатель» принять и оплатить товар – Сырье в ассортименте." in html
    assert "1.3. Общая сумма настоящего Договора составляет: 20 000 000 000 (двадцать миллиардов) сум 00 тийин" in html
    assert "2.2. В случае нарушения сроков перечисления денежных средств на счет «Поставщика» более чем на 1 банковских дней" in html
    assert "2.3. «Поставщик» обязуется осуществить поставку продукции в течение 5 банковских дней" in html
    assert "2.6. Вид транспорта и базис поставки: самовывоз со склада «Поставщика»" in html
    assert "на основании доверенности № 4 от 05.01.2026" in html
    assert "СПЕЦИФИКАЦИЯ" not in html


def test_the_global_contract_has_its_ten_sections() -> None:
    assert _sections(_render(_GLOBAL)) == [
        "1. ПРЕДМЕТ ДОГОВОРА",
        "2. УСЛОВИЯ ПОСТАВКИ И РАСЧЕТОВ",
        "3. ОТВЕТСТВЕННОСТЬ СТОРОН",
        "4. ТАРА И УПАКОВКА",
        "5. КАЧЕСТВО, КОМПЛЕКТНОСТЬ И ГАРАНТИИ",
        "6. СРОК ДЕЙСТВИЯ ДОГОВОРА",
        "7. ПОРЯДОК РАЗРЕШЕНИЯ СПОРОВ",
        "8. ФОРС-МАЖОР",
        "9. ПРОЧИЕ УСЛОВИЯ",
        "10. ЮРИДИЧЕСКИЕ АДРЕСА И РЕКВИЗИТЫ СТОРОН",
    ]


def test_the_global_variant_clauses_and_its_specification() -> None:
    html = _render(_GLOBAL)
    assert "1.1. «Поставщик» обязуется поставить, а «Покупатель» принять и оплатить товар – МОНОЭТИЛЕНГЛИКОЛЬ МЭГ." in html
    assert (
        "1.3. Общая сумма настоящего Договора составляет: 922 383 000 "
        "(девятьсот двадцать два миллиона триста восемьдесят три тысячи) сум 00 тийин"
    ) in html
    assert "2.2. «Покупатель» обязуется произвести оплату 100% стоимости товара по графику платежей" in html
    assert "2.3. В случае нарушения сроков перечисления денежных средств на счет «Поставщика» более чем на 10 банковских дней, «Поставщик» имеет право пересмотреть цены" in html
    assert "со дня первой части оплаты" in html
    assert "4.1. Товар поставляется без упаковки, наливом." in html
    assert "Самовывоз осуществляется по адресу: Ташкент, станция «Уртааул»." in html
    # The specification annex, as in the original.
    assert "СПЕЦИФИКАЦИЯ" in html
    assert "922 383 000" in html and "98 826 750" in html
    assert "<td>кг</td>" in html


@pytest.mark.parametrize("variables", [_AKFA, _GLOBAL], ids=["akfa", "global"])
def test_nothing_is_left_unrendered(variables: dict[str, str]) -> None:
    html = _render(variables)
    assert "{{" not in html and "}}" not in html


def test_a_buyer_initiator_keeps_the_supplier_in_the_supplier_seat() -> None:
    html = contract_render.render_contract_html(
        _BODY, {**_AKFA, "initiator_side": "buyer"}, _BUYER, _SUPPLIER,
        contract_public_id="x", generated_at="t",
    )
    assert html.index("СП ООО «MGBUS», именуемое в дальнейшем «Поставщик»") >= 0


@pytest.mark.parametrize("kind", ["frame", "one_off"])
def test_the_body_validates_against_its_schema(kind: str) -> None:
    report = template_service.validate_body(_BODY, "contract", _mgbus_schema(kind))
    assert report.ok, report.unknown


def test_no_requisites_or_annex_go_to_didox() -> None:
    """Didox draws the parties, the goods table and the signatures itself."""
    from app.domains.edi.contract_docs import sections_from_html  # noqa: PLC0415

    titles = [title for title, _ in sections_from_html(_render(_GLOBAL))]
    assert titles[-1] == "ПРОЧИЕ УСЛОВИЯ"
    assert all("РЕКВИЗИТЫ" not in t and "СПЕЦИФИКАЦИЯ" not in t for t in titles)
