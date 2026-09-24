"""Sums as a contract writes them: grouped digits, words, and the VAT split.

Pure, no dependencies. The shapes are the ones in the real MGBUS documents
(`docs/deals_documents/`): «922 383 000 (девятьсот двадцать два миллиона …) сум
00 тийин», and a specification line priced WITH VAT whose price and sum without
VAT are derived from it — 16 300 сум/кг → 14 553,57 сум/кг без НДС.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass

_CENT = decimal.Decimal("0.01")

_ONES_M = ("", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_ONES_F = ("", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_TEENS = (
    "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
    "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать",
)
_TENS = (
    "", "", "двадцать", "тридцать", "сорок", "пятьдесят",
    "шестьдесят", "семьдесят", "восемьдесят", "девяносто",
)
_HUNDREDS = (
    "", "сто", "двести", "триста", "четыреста", "пятьсот",
    "шестьсот", "семьсот", "восемьсот", "девятьсот",
)

#: (one, few, many, feminine) for each power of a thousand, units first.
_SCALES: tuple[tuple[str, str, str, bool], ...] = (
    ("", "", "", False),
    ("тысяча", "тысячи", "тысяч", True),
    ("миллион", "миллиона", "миллионов", False),
    ("миллиард", "миллиарда", "миллиардов", False),
    ("триллион", "триллиона", "триллионов", False),
)


def _plural(n: int, one: str, few: str, many: str) -> str:
    if 11 <= n % 100 <= 14:
        return many
    if n % 10 == 1:
        return one
    if 2 <= n % 10 <= 4:
        return few
    return many


def _triad(n: int, feminine: bool) -> list[str]:
    words = [_HUNDREDS[n // 100]]
    rest = n % 100
    if 10 <= rest <= 19:
        words.append(_TEENS[rest - 10])
    else:
        words.append(_TENS[rest // 10])
        words.append((_ONES_F if feminine else _ONES_M)[rest % 10])
    return [w for w in words if w]


def in_words(value: int) -> str:
    """A whole number in Russian words — «девятьсот двадцать два миллиона …»."""
    if value == 0:
        return "ноль"
    if value < 0:
        return "минус " + in_words(-value)
    groups: list[int] = []
    while value:
        groups.append(value % 1000)
        value //= 1000
    if len(groups) > len(_SCALES):
        raise ValueError("number too large to write in words")
    words: list[str] = []
    for power in range(len(groups) - 1, -1, -1):
        n = groups[power]
        if n == 0:
            continue
        one, few, many, feminine = _SCALES[power]
        words.extend(_triad(n, feminine))
        if power:
            words.append(_plural(n, one, few, many))
    return " ".join(words)


def grouped(value: decimal.Decimal) -> str:
    """`1746428571.43` → «1 746 428 571,43»; whole numbers keep no decimals."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    whole = int(value)
    digits = f"{whole:,}".replace(",", " ")
    fraction = value - whole
    if fraction == 0:
        return sign + digits
    cents = f"{value.quantize(_CENT, rounding=decimal.ROUND_HALF_UP):f}".split(".")[1]
    return f"{sign}{digits},{cents}"


def sum_phrase(value: decimal.Decimal) -> str:
    """«922 383 000 (девятьсот двадцать два миллиона …) сум 00 тийин»."""
    value = value.quantize(_CENT, rounding=decimal.ROUND_HALF_UP)
    whole = int(value)
    tiyin = int((value - whole) * 100)
    return f"{grouped(decimal.Decimal(whole))} ({in_words(whole)}) сум {tiyin:02d} тийин"


@dataclass(frozen=True)
class VatLine:
    amount_with_vat: decimal.Decimal
    vat_sum: decimal.Decimal
    amount_without_vat: decimal.Decimal
    price_without_vat: decimal.Decimal


def vat_line(
    *, qty: decimal.Decimal, price_with_vat: decimal.Decimal, vat_rate: int | None
) -> VatLine:
    """Split a line priced WITH VAT, the way the MGBUS specifications do.

    The sum with VAT is the agreed figure; VAT is carved out of it
    (`sum × rate / (100 + rate)`), never added on top, so the total the parties
    signed is the total the document shows.
    """
    total = (qty * price_with_vat).quantize(_CENT, rounding=decimal.ROUND_HALF_UP)
    if vat_rate is None or vat_rate == 0:
        vat = decimal.Decimal("0.00")
    else:
        rate = decimal.Decimal(vat_rate)
        vat = (total * rate / (100 + rate)).quantize(_CENT, rounding=decimal.ROUND_HALF_UP)
    without = total - vat
    price = (without / qty).quantize(_CENT, rounding=decimal.ROUND_HALF_UP) if qty else without
    return VatLine(
        amount_with_vat=total, vat_sum=vat, amount_without_vat=without, price_without_vat=price
    )


def net_line(
    *, qty: decimal.Decimal, price_without_vat: decimal.Decimal, vat_rate: int | None
) -> VatLine:
    """A line priced WITHOUT VAT, the way an ЭСФ states it.

    `Count × Summa`, then VAT added on top — exactly `payloads._totals`, so a
    specification priced this way and its ЭСФ agree to the tiyin. The price is
    held to 2 decimals because that is all an ЭСФ accepts.
    """
    price = price_without_vat.quantize(_CENT, rounding=decimal.ROUND_HALF_UP)
    without = (qty * price).quantize(_CENT, rounding=decimal.ROUND_HALF_UP)
    if vat_rate is None or vat_rate == 0:
        vat = decimal.Decimal("0.00")
    else:
        vat = (without * decimal.Decimal(vat_rate) / 100).quantize(
            _CENT, rounding=decimal.ROUND_HALF_UP
        )
    return VatLine(
        amount_with_vat=without + vat, vat_sum=vat, amount_without_vat=without,
        price_without_vat=price,
    )
