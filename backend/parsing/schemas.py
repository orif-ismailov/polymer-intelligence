"""
Pydantic schemas for the Phase 5 AI extraction contract.

ExtractionResult is the fixed output schema for one LLM call: classify a
Telegram message as relevant/not, and if relevant extract the polymer market
signal fields. Validated with Pydantic 2 via instructor Mode.TOOLS.

Enum values are identical to the DB ENUMs (app.models.enums.SignalKind and
app.models.enums.Urgency) so extraction output maps directly to the signals
table without conversion.

CRITICAL INVARIANTS (threat model T-05-01):
- is_relevant=False ⇒ all market fields MUST be null (irrelevant_fields_must_be_null)
- currency is uppercased and validated as exactly 3 capital ASCII letters (normalise_currency)
- volume and price are Decimal to avoid floating-point comparison bugs in eval
- confidence < CONFIDENCE_REVIEW_THRESHOLD routes the signal to needs_review queue

Downstream consumers:
- parsing.extractor (05-03) — calls extract_signal() → ExtractionResult
- tasks.parse_tasks (05-04) — checks result.confidence < CONFIDENCE_REVIEW_THRESHOLD
- tests.parsing.test_extractor (05-05) — golden-set per-field assertions
"""

from __future__ import annotations

import re
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enumerations matching DB ENUMs exactly
# (values must stay in sync with backend/app/models/enums.py;
#  tests/parsing/test_schemas.py::TestEnumParity asserts parity)
# ---------------------------------------------------------------------------


class SignalKind(str, Enum):
    """Signal kind — matches signal_kind PostgreSQL ENUM verbatim."""

    BUY_REQUEST = "buy_request"
    SELL_OFFER  = "sell_offer"
    DEAL        = "deal"
    PRICE_QUOTE = "price_quote"
    NEWS        = "news"


class UrgencyLevel(str, Enum):
    """Urgency level — matches urgency PostgreSQL ENUM verbatim."""

    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


# ---------------------------------------------------------------------------
# Field-level confidence (per-field; used in eval for per-field precision)
# ---------------------------------------------------------------------------


class FieldConfidence(BaseModel):
    """Confidence score per extracted field (0.0–1.0).

    The LLM is instructed to populate this alongside each value.
    Used in eval: field-level precision is calculated per field.
    """

    product:      float = Field(ge=0.0, le=1.0, default=0.0)
    grade_text:   float = Field(ge=0.0, le=1.0, default=0.0)
    volume:       float = Field(ge=0.0, le=1.0, default=0.0)
    price:        float = Field(ge=0.0, le=1.0, default=0.0)
    currency:     float = Field(ge=0.0, le=1.0, default=0.0)
    counterparty: float = Field(ge=0.0, le=1.0, default=0.0)
    region:       float = Field(ge=0.0, le=1.0, default=0.0)
    urgency:      float = Field(ge=0.0, le=1.0, default=0.0)


# ---------------------------------------------------------------------------
# Main extraction schema
# ---------------------------------------------------------------------------


class ExtractionResult(BaseModel):
    """
    Single-call extraction result for one Telegram message.

    Invariants enforced by validators:
    - If is_relevant=False, all market fields MUST be null.
    - volume and price are Decimal to avoid floating-point comparison bugs in eval.
    - currency is uppercased and validated as 3-char ISO 4217 code.
    - confidence is the overall score; <0.5 routes to needs_review queue.
    """

    # --- Relevance gate ---
    is_relevant: bool = Field(
        description="True if the message contains a polymer market signal."
    )

    # --- Signal classification (null when is_relevant=False) ---
    kind: SignalKind | None = Field(
        default=None,
        description="Signal type matching signal_kind DB enum.",
    )

    # --- Product fields ---
    product: str | None = Field(
        default=None,
        max_length=32,
        description="Polymer code: PP, HDPE, LDPE, LLDPE, PVC, PET, PS, ABS, etc.",
    )
    grade_text: str | None = Field(
        default=None,
        max_length=128,
        description="Grade/specification verbatim from source. Null if not mentioned.",
    )

    # --- Trade parameters ---
    volume: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        description="Volume in metric tonnes. Null if not stated.",
    )
    volume_unit: str = Field(
        default="MT",
        description="Always MT for Phase 5.",
    )
    price: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        description="Unit price. Null if not stated.",
    )
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code: USD, UZS, RUB, CNY, EUR.",
    )
    region: str | None = Field(
        default=None,
        max_length=64,
        description="Market/region of the event. Null if not determinable.",
    )

    # --- Counterparty ---
    counterparty_text: str | None = Field(
        default=None,
        max_length=256,
        description="Counterparty name verbatim. Null if not mentioned.",
    )

    # --- AI enrichment ---
    urgency: UrgencyLevel | None = Field(
        default=None,
        description="Urgency level inferred from language cues.",
    )
    lead_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Lead quality score 0–1. "
            "Populated by lead-scoring pass, not extraction."
        ),
    )

    # --- Confidence ---
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Overall extraction confidence. "
            "<0.5 routes to needs_review queue."
        ),
    )
    field_confidence: FieldConfidence = Field(
        default_factory=FieldConfidence,
        description="Per-field confidence scores.",
    )

    # --- Temporal fields (for stale-repost handling; AI-SPEC §1b FM#5 / D14) ---
    event_at: str | None = Field(
        default=None,
        description=(
            "Original event timestamp ISO-8601 (UTC). "
            "For forwarded messages set to fwd_from.date, not fetch time. "
            "Null if not determinable."
        ),
    )
    is_forwarded: bool = Field(
        default=False,
        description=(
            "True if the Telegram message was forwarded from another channel. "
            "Set by the userbot from fwd_from, not by the LLM."
        ),
    )

    # ---------------------------------------------------------------------------
    # Validators (threat model T-05-01: structural firewall against fabricated records)
    # ---------------------------------------------------------------------------

    @field_validator("currency")
    @classmethod
    def normalise_currency(cls, v: str | None) -> str | None:
        """Uppercase and validate currency as exactly 3 ASCII capital letters.

        Accepts: 'usd' → 'USD', 'UZS' → 'UZS'.
        Rejects: 'DOLLAR', 'US', 'USD1' (not 3-letter ISO codes).
        """
        if v is None:
            return None
        upper = v.upper().strip()
        if not re.fullmatch(r"[A-Z]{3}", upper):
            raise ValueError(
                f"currency must be a 3-letter ISO 4217 code (e.g. USD, UZS, RUB), "
                f"got {v!r}"
            )
        return upper

    @model_validator(mode="after")
    def irrelevant_fields_must_be_null(self) -> ExtractionResult:
        """If the message is not relevant, no market fields should be populated.

        This catches the hallucination pattern where the model invents values
        for an irrelevant message (Critical FM#1 in AI-SPEC §1).
        """
        if not self.is_relevant:
            non_null = [
                f
                for f in (
                    "kind",
                    "product",
                    "grade_text",
                    "volume",
                    "price",
                    "currency",
                    "counterparty_text",
                    "urgency",
                )
                if getattr(self, f) is not None
            ]
            if non_null:
                raise ValueError(
                    f"is_relevant=False but market fields are populated: {non_null}. "
                    "Set all market fields to null for irrelevant messages."
                )
        return self


# ---------------------------------------------------------------------------
# Sentinel for token budget exhaustion
# ---------------------------------------------------------------------------


class BudgetExceeded(Exception):
    """Raised by parsing.budget.check_and_reserve_tokens() when daily limit is hit.

    Caller must degrade to rule-based fallback and enqueue for nightly catch-up.
    """


# ---------------------------------------------------------------------------
# Review threshold constant (used in task orchestrator)
# ---------------------------------------------------------------------------

CONFIDENCE_REVIEW_THRESHOLD: float = 0.5
"""Signals with confidence < this value are routed to the needs_review queue."""
