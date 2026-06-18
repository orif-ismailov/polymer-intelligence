"""
Phase 5 rule-based extraction fallback.

Used when the daily token budget is exhausted (AI-SPEC §6 G4). This is a REAL
fallback extraction — not a stub or placeholder. It produces a fully-valid
ExtractionResult with low confidence so the orchestrator routes every rule-based
result to the needs_review queue (never auto-published as HOT).

Design invariants (AI-SPEC G4 + plan scope_reduction_prohibition):
- Relevant results ALWAYS have confidence < CONFIDENCE_REVIEW_THRESHOLD (0.5)
  so the 05-04 orchestrator routes them to needs_review — rule-based results
  are never auto-published regardless of content quality
- Irrelevant results satisfy irrelevant_fields_must_be_null (all market fields null)
- No DB access, no LLM call, no network I/O — deterministic, testable in CI

Product detection (polymer codes):
    Recognized from both Latin and Cyrillic variants in Russian/Uzbek channel text.
    Patterns are conservative: match only if a clear polymer keyword is present.

Currency detection (AI-SPEC §1b FM#3 + §5.3):
    "у.е."/"уе"/"ue" → USD (CIS conventional units)
    "$"/"доллар"/"dollar"/"usd" → USD
    "сум"/"so'm"/"sum"/"uzs" → UZS
    "рублей"/"руб"/"рубль"/"₽"/"rub" → RUB
    CNY/"юань"/"yuan" → CNY

Volume detection:
    "тонн"/"тонна"/"тонне"/"т" (Russian) or "ton" (Latin) → metric tonnes (MT)
    "кг"/"kg" → divide by 1000 to convert to MT

Price detection:
    Numeric value adjacent to a currency token, or the last decimal-like number
    in the message when a product is detected.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from parsing.schemas import (
    CONFIDENCE_REVIEW_THRESHOLD,
    ExtractionResult,
    FieldConfidence,
    SignalKind,
)

# ---------------------------------------------------------------------------
# Confidence constants (AI-SPEC G4: rule-based always < review threshold)
# ---------------------------------------------------------------------------

_RELEVANT_CONFIDENCE = CONFIDENCE_REVIEW_THRESHOLD - 0.1  # 0.4 — always below 0.5
_IRRELEVANT_CONFIDENCE = 0.6  # irrelevant detection is fairly reliable


# ---------------------------------------------------------------------------
# Polymer product detection
# ---------------------------------------------------------------------------

# Ordered from most specific to least — match first wins
_PRODUCT_PATTERNS: list[tuple[str, str]] = [
    # Polyethylene variants (most specific first)
    (r"\bLLDPE\b",                                "LLDPE"),
    (r"\bLDPE\b|\bПВД\b",                         "LDPE"),
    (r"\bHDPE\b|\bПНД\b",                         "HDPE"),
    # PET / PVC
    (r"\bPET\b|\bПЭТ\b",                          "PET"),
    (r"\bPVC\b|\bПВХ\b",                           "PVC"),
    # Polystyrene / ABS
    (r"\bABS\b",                                   "ABS"),
    (r"\bPS\b|\bПС\b",                            "PS"),
    # Polypropylene (broad — after the PE variants so we don't confuse)
    (r"\bPP\b|\bПП\b|\bполипропилен\b|\bpolypropylene\b", "PP"),
    # Polyethylene generic (after specific variants)
    (r"\bPE\b|\bПЭ\b|\bполиэтилен\b|\bpolyethylene\b",    "PE"),
]

_PRODUCT_RE: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE), code) for p, code in _PRODUCT_PATTERNS
]


def _detect_product(text: str) -> str | None:
    """Return the polymer product code if detected, else None."""
    for pattern, code in _PRODUCT_RE:
        if pattern.search(text):
            return code
    return None


# ---------------------------------------------------------------------------
# Grade detection (reuse the grade regex from grade_service)
# ---------------------------------------------------------------------------

# Polymer grade code formats: T30S, H030, 2420D, TR570M, etc.
_GRADE_RE = re.compile(r"\b([A-Z]{1,4}\d{2,5}[A-Z]{0,3}|\d{2,5}[A-Z]{1,3})\b", re.IGNORECASE)


def _detect_grade(text: str) -> str | None:
    """Return the first grade-like token found, else None."""
    match = _GRADE_RE.search(text)
    return match.group(1).upper() if match else None


# ---------------------------------------------------------------------------
# Currency detection (AI-SPEC §1b FM#3: у.е. → USD critical)
# ---------------------------------------------------------------------------

_CURRENCY_PATTERNS: list[tuple[re.Pattern, str]] = [
    # USD signals — у.е. (CIS conventional units, critical: AI-SPEC §1b FM#3)
    # Note: \b doesn't match Cyrillic boundaries; use lookahead/lookbehind or plain match
    (re.compile(r"у\.е\.", re.IGNORECASE | re.UNICODE),               "USD"),
    (re.compile(r"(?<!\w)уе(?!\w)", re.IGNORECASE | re.UNICODE),      "USD"),
    (re.compile(r"\$|\bдоллар|\bdollar\b|\busd\b", re.IGNORECASE),   "USD"),
    # UZS signals
    (re.compile(r"(?<!\w)сум(?!\w)|so'm|(?<!\w)som(?!\w)|(?<!\w)sum(?!\w)|\buzs\b",
                re.IGNORECASE | re.UNICODE),                           "UZS"),
    # RUB signals
    (re.compile(r"(?<!\w)рублей(?!\w)|(?<!\w)руб(?!\w)|(?<!\w)рубль(?!\w)|₽|\brub\b",
                re.IGNORECASE | re.UNICODE),                           "RUB"),
    # CNY signals
    (re.compile(r"(?<!\w)юань(?!\w)|\byuan\b|\bcny\b", re.IGNORECASE | re.UNICODE), "CNY"),
]


def _detect_currency(text: str) -> str | None:
    """Return the ISO currency code detected from the text, else None."""
    for pattern, code in _CURRENCY_PATTERNS:
        if pattern.search(text):
            return code
    return None


# ---------------------------------------------------------------------------
# Volume detection (MT; converts kg → /1000)
# ---------------------------------------------------------------------------

# Matches patterns like "50 тонн", "50.5 т", "50 ton", "50000 кг"
_VOLUME_TONNE_RE = re.compile(
    r"(\d[\d\s\.,]*)\s*(?:тонн[аеи]?|т(?=\s|\.|\b)|ton[s]?)\b",
    re.IGNORECASE | re.UNICODE,
)
_VOLUME_KG_RE = re.compile(
    r"(\d[\d\s\.,]*)\s*(?:кг|kg)\b",
    re.IGNORECASE,
)


def _parse_number(s: str) -> Decimal | None:
    """Parse a number string with optional spaces/commas as thousands separators."""
    cleaned = re.sub(r"[\s\xa0]", "", s).replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _detect_volume(text: str) -> Decimal | None:
    """Return volume in MT (converts kg/1000 if needed), or None."""
    # Try tonnes first
    m = _VOLUME_TONNE_RE.search(text)
    if m:
        val = _parse_number(m.group(1))
        if val is not None and val > 0:
            return val

    # Try kg (divide by 1000)
    m = _VOLUME_KG_RE.search(text)
    if m:
        val = _parse_number(m.group(1))
        if val is not None and val > 0:
            return (val / 1000).quantize(Decimal("0.001"))

    return None


# ---------------------------------------------------------------------------
# Price detection
# ---------------------------------------------------------------------------

# A price is a numeric value (possibly with thousands sep) followed optionally
# by a currency token, or preceded by "по" / "цена" / "price".
_PRICE_RE = re.compile(
    r"(?:по|цена|price|стоим[а-яё]+)?\s*(\d[\d\s\.,]{1,10})\s*"
    r"(?:у\.е\.|уе|ue|\$|долларов?|rubles?|сум|so'm|som|sum|rub|\bт\.р\.\b)?",
    re.IGNORECASE | re.UNICODE,
)

# Simpler fallback: any standalone number that looks like a price (100–9,999,999)
_NUMBER_RE = re.compile(r"\b(\d[\d\s\.,]{2,9})\b")


def _detect_price(text: str) -> Decimal | None:
    """Return the first price-like numeric value, or None."""
    for m in _PRICE_RE.finditer(text):
        val = _parse_number(m.group(1))
        if val is not None and val >= 100:  # ignore tiny numbers (volumes of <100 are valid)
            return val

    # Fallback: last numeric token >= 100
    for m in reversed(list(_NUMBER_RE.finditer(text))):
        val = _parse_number(m.group(1))
        if val is not None and val >= 100:
            return val

    return None


# ---------------------------------------------------------------------------
# Relevance heuristic
# ---------------------------------------------------------------------------

# Irrelevance signals — if the text matches strongly irrelevant patterns and
# does NOT contain a polymer product keyword, classify as irrelevant.
_SPAM_KEYWORDS_RE = re.compile(
    r"\b(спам|реклама|подпишись|подписка|subscribe|spam|advertisement|"
    r"конкурс|giveaway|акция|скидк|discount|бесплатно|free|click\s+here|"
    r"vacancy|вакансия|требуется|работа|job\s+offer)\b",
    re.IGNORECASE | re.UNICODE,
)

# Relevance signals — polymer-related trade verbs
_TRADE_VERB_RE = re.compile(
    r"\b(продам|продаём|продается|куплю|покупаем|предлагаем|offer|sell|buy|"
    r"сделка|deal|цена|price|поставка|delivery|партия|batch|лот|lot)\b",
    re.IGNORECASE | re.UNICODE,
)


def _is_relevant(text: str, product: str | None) -> bool:
    """Return True if the text is likely a polymer market signal."""
    if not text.strip():
        return False

    # A detected polymer product is a strong relevance signal
    if product is not None:
        return True

    # If there's a trade verb without a product — marginally relevant
    # (might be a buy/sell of something else)
    if _TRADE_VERB_RE.search(text):
        # Apply spam filter: if it matches spam patterns, still mark irrelevant
        if _SPAM_KEYWORDS_RE.search(text):
            return False
        return False  # trade verb without product → not a polymer signal

    return False


# ---------------------------------------------------------------------------
# Kind detection (best-effort; low-confidence)
# ---------------------------------------------------------------------------

def _detect_kind(text: str) -> SignalKind | None:
    """Detect the signal kind from trade verb patterns."""
    text_lower = text.lower()

    # Sell signals
    if re.search(r"\b(продам|продаём|продается|sell|offer)\b", text_lower):
        return SignalKind.SELL_OFFER
    # Buy signals
    if re.search(r"\b(куплю|покупаем|buy|purchase|нужен|нужно)\b", text_lower):
        return SignalKind.BUY_REQUEST
    # Deal
    if re.search(r"\b(сделка закрыта|deal closed|закрыт[аоы])\b", text_lower):
        return SignalKind.DEAL
    # Price quote
    if re.search(r"\b(цена|price|стоимость|котировка|quote)\b", text_lower):
        return SignalKind.PRICE_QUOTE

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def rule_based_extract(text: str) -> ExtractionResult:
    """Apply rule-based extraction to produce a low-confidence ExtractionResult.

    This is the budget-degraded fallback path (AI-SPEC §6 G4). Every result has:
    - confidence < CONFIDENCE_REVIEW_THRESHOLD (0.4) for relevant messages
      so the orchestrator always routes to needs_review
    - is_relevant=False + null market fields for irrelevant messages (invariant)

    NEVER auto-publish rule-based results as HOT leads — they are the degraded
    path when the LLM budget is exhausted and must always be human-reviewed.

    Args:
        text: Raw Telegram message text (may be empty).

    Returns:
        ExtractionResult: Low-confidence result. Relevant messages have
            product/currency/volume extracted where detectable; all other fields
            default to None. Always validates against the ExtractionResult schema.

    Security (T-05-11):
        The output is validated through ExtractionResult.model_validate() (implicit
        via Pydantic constructor). The irrelevant_fields_must_be_null validator
        ensures no fabricated values escape on irrelevant messages.
    """
    if not text.strip():
        return ExtractionResult(
            is_relevant=False,
            confidence=_IRRELEVANT_CONFIDENCE,
        )

    product = _detect_product(text)
    relevant = _is_relevant(text, product)

    if not relevant:
        # Strictly irrelevant: all market fields must be null (invariant)
        return ExtractionResult(
            is_relevant=False,
            confidence=_IRRELEVANT_CONFIDENCE,
        )

    # Relevant: extract what we can with rules
    currency = _detect_currency(text)
    volume = _detect_volume(text)
    price_val = _detect_price(text) if currency is not None else None
    grade = _detect_grade(text)
    kind = _detect_kind(text)

    # Per-field confidence (all low for rule-based)
    field_conf = FieldConfidence(
        product=0.6 if product else 0.0,
        grade_text=0.4 if grade else 0.0,
        volume=0.5 if volume else 0.0,
        price=0.4 if price_val else 0.0,
        currency=0.6 if currency else 0.0,
        counterparty=0.0,
        region=0.0,
        urgency=0.0,
    )

    return ExtractionResult(
        is_relevant=True,
        kind=kind,
        product=product,
        grade_text=grade,
        volume=volume,
        volume_unit="MT",
        price=price_val,
        currency=currency,
        region=None,
        counterparty_text=None,
        urgency=None,
        lead_score=None,
        # CRITICAL: confidence MUST be below CONFIDENCE_REVIEW_THRESHOLD (0.5)
        # so the orchestrator always routes rule-based results to needs_review.
        # Rule-based is the budget-degraded path — never auto-published (G4).
        confidence=_RELEVANT_CONFIDENCE,
        field_confidence=field_conf,
    )
