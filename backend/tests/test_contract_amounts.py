"""Sums in words and the VAT split, pinned to the real MGBUS documents (24.09.2026).

The figures are copied from `docs/deals_documents/`: a specification is priced
WITH VAT (16 300 сум/кг), and the price and sum without VAT are derived from it,
exactly as the AKFA specification shows them.
"""

from __future__ import annotations

import decimal

import pytest

from app.domains.contracts import amounts

D = decimal.Decimal


@pytest.mark.parametrize(
    ("value", "words"),
    [
        (922_383_000, "девятьсот двадцать два миллиона триста восемьдесят три тысячи"),
        (1_956_000_000, "один миллиард девятьсот пятьдесят шесть миллионов"),
        (20_000_000_000, "двадцать миллиардов"),
        (0, "ноль"),
        (1, "один"),
        (2_001, "две тысячи один"),
        (21_000, "двадцать одна тысяча"),
        (1_000_000, "один миллион"),
        (115, "сто пятнадцать"),
        (4_004_004, "четыре миллиона четыре тысячи четыре"),
    ],
)
def test_integer_in_words(value: int, words: str) -> None:
    assert amounts.in_words(value) == words


def test_grouped_digits() -> None:
    assert amounts.grouped(D("922383000")) == "922 383 000"
    assert amounts.grouped(D("1746428571.43")) == "1 746 428 571,43"
    assert amounts.grouped(D("14553.57")) == "14 553,57"


def test_the_akfa_specification_line() -> None:
    """120 000 кг at 16 300 сум/кг with VAT — every column of Спецификация № 01."""
    line = amounts.vat_line(qty=D("120000"), price_with_vat=D("16300"), vat_rate=12)
    assert line.amount_with_vat == D("1956000000.00")
    assert line.vat_sum == D("209571428.57")
    assert line.amount_without_vat == D("1746428571.43")
    assert line.price_without_vat == D("14553.57")


def test_the_global_petrochemical_line() -> None:
    line = amounts.vat_line(qty=D("120000"), price_with_vat=D("7686.525"), vat_rate=12)
    assert line.amount_with_vat == D("922383000.00")
    assert line.vat_sum == D("98826750.00")


def test_without_vat() -> None:
    line = amounts.vat_line(qty=D("10"), price_with_vat=D("100"), vat_rate=None)
    assert (line.amount_with_vat, line.vat_sum, line.amount_without_vat) == (
        D("1000.00"), D("0.00"), D("1000.00")
    )


def test_the_sum_as_a_contract_writes_it() -> None:
    assert amounts.sum_phrase(D("922383000")) == (
        "922 383 000 (девятьсот двадцать два миллиона триста восемьдесят три тысячи) сум 00 тийин"
    )
    assert amounts.sum_phrase(D("1500.5")) == "1 500 (одна тысяча пятьсот) сум 50 тийин"


def test_a_line_priced_without_vat_agrees_with_its_esf() -> None:
    """14 553,57 without VAT: the ЭСФ's own arithmetic, to the tiyin."""
    line = amounts.net_line(qty=D("120000"), price_without_vat=D("14553.57"), vat_rate=12)
    assert line.amount_without_vat == D("1746428400.00")
    assert line.vat_sum == D("209571408.00")
    assert line.amount_with_vat == D("1955999808.00")
