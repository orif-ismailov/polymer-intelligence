"""
Pydantic schema for the News-Intelligence extraction contract (Phase 7).

NewsArticle is the fixed output schema for one LLM call over a news item from an
approved source (Telegram channel, RSS, company/gov site). It mirrors the STEP-3
fields of the IMEX AI news spec: headline, classification, country, related products,
companies, importance, market impact, and a short "why it matters" summary.

Kept separate from parsing.schemas.ExtractionResult (which is trade-signal shaped):
a news item is NOT a buy/sell/deal signal, so it gets its own contract. Validated
with Pydantic 2 via instructor Mode.TOOLS, same as the signal extractor.

Design notes:
- The category vocabulary is controlled but OPEN: `category` is the single primary
  theme and `tags` are all applicable labels. The allowed values live in the prompt
  (news_extract_vN.md), not a rigid DB enum, so the taxonomy can evolve without a
  migration. NEWS_CATEGORIES below is the reference list the prompt is generated from.
- Importance / market impact ARE small fixed enums (they drive ranking + colour).
- is_relevant=False ⇒ everything else may be empty; the caller drops the item.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

# Reference taxonomy (STEP 2 of the spec). The prompt lists these; extraction is soft —
# the model may emit a close variant, which downstream normalization can map.
NEWS_CATEGORIES: tuple[str, ...] = (
    "market_prices", "petrochemicals", "polymers", "polyethylene", "polypropylene",
    "pvc", "pet", "abs", "ps", "styrene", "methanol", "meg",
    "energy", "oil", "natural_gas", "refineries",
    "production", "plant_shutdown", "maintenance",
    "logistics", "ports", "railways", "customs", "import", "export", "trade",
    "technology", "artificial_intelligence", "market_analysis", "investment",
    "factories", "new_projects",
)


def _cap_words(value: str | None, limit: int) -> str | None:
    """Soft-cap a text field at `limit` words; never fail extraction."""
    if value is None:
        return None
    words = value.split()
    return " ".join(words[:limit]) if len(words) > limit else value


class NewsImportance(str, Enum):
    """How much a buyer/supplier/trader should care."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NewsMarketImpact(str, Enum):
    """Directional effect on the petrochemical market."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class NewsLocalized(BaseModel):
    """The display fields of one article rendered in a single language (ru/uz/en)."""

    headline: str | None = Field(default=None, description="Localized headline.")
    summary: str | None = Field(default=None, description="Localized short summary.")
    analysis: str | None = Field(default=None, description="Localized AI market analysis.")
    recommendation: str | None = Field(default=None, description="Localized business recommendation.")


class NewsI18n(BaseModel):
    """Localized variants of the article for the three primary UI languages."""

    ru: NewsLocalized | None = Field(default=None, description="Russian variant.")
    uz: NewsLocalized | None = Field(default=None, description="Uzbek variant.")
    en: NewsLocalized | None = Field(default=None, description="English variant.")


class NewsArticle(BaseModel):
    """One classified news article (STEP 3 of the IMEX AI news spec)."""

    is_relevant: bool = Field(
        description=(
            "True only for petrochemical/polymer/energy/logistics/trade news that matters "
            "to the market. False for ads, politics (unless it directly moves the market), "
            "crypto, entertainment, or off-topic content — then leave the rest empty."
        )
    )
    headline: str | None = Field(default=None, description="A concise, factual headline (max ~120 chars).")
    category: str | None = Field(default=None, description="Primary theme, from the allowed category list.")
    tags: list[str] = Field(default_factory=list, description="All applicable category labels.")
    country: str | None = Field(default=None, description="Primary country (e.g. Uzbekistan, Russia, China).")
    countries: list[str] = Field(
        default_factory=list,
        description="All affected countries mentioned (primary first). [] if global/unclear.",
    )
    related_products: list[str] = Field(
        default_factory=list,
        description="Canonical product codes touched by the news (e.g. PP, HDPE, PVC, PET, methanol).",
    )
    companies: list[str] = Field(default_factory=list, description="Companies/plants explicitly mentioned.")
    importance: NewsImportance | None = Field(default=None, description="high | medium | low.")
    market_impact: NewsMarketImpact | None = Field(
        default=None, description="positive | negative | neutral effect on the market."
    )
    summary: str | None = Field(
        default=None,
        description="≤120 words explaining why this matters for buyers, suppliers and traders.",
    )
    analysis: str | None = Field(
        default=None,
        description=(
            "≤160 words of AI market analysis covering: what happened, why it matters, the "
            "effect on the petrochemical market, on Uzbekistan, on buyers, and on suppliers."
        ),
    )
    recommendation: str | None = Field(
        default=None,
        description="ONE concise, professional business recommendation (≤40 words).",
    )
    language: str | None = Field(
        default=None,
        description="Detected language of the source article as an ISO code: ru, uz, en, or other.",
    )
    i18n: NewsI18n | None = Field(
        default=None,
        description="headline/summary/analysis/recommendation localized into ru, uz and en.",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Model confidence in the classification.")

    @field_validator("summary")
    @classmethod
    def _cap_summary_words(cls, v: str | None) -> str | None:
        """Soft-cap the summary at 120 words (the spec limit); never fail extraction."""
        return _cap_words(v, 120)

    @field_validator("analysis")
    @classmethod
    def _cap_analysis_words(cls, v: str | None) -> str | None:
        return _cap_words(v, 160)

    @field_validator("recommendation")
    @classmethod
    def _cap_recommendation_words(cls, v: str | None) -> str | None:
        return _cap_words(v, 40)

    @model_validator(mode="after")
    def _irrelevant_is_empty(self) -> NewsArticle:
        """is_relevant=False ⇒ the article carries no classification payload."""
        if not self.is_relevant:
            self.headline = None
            self.category = None
            self.tags = []
            self.country = None
            self.countries = []
            self.related_products = []
            self.companies = []
            self.importance = None
            self.market_impact = None
            self.summary = None
            self.analysis = None
            self.recommendation = None
            self.language = None
            self.i18n = None
        return self


# confidence below this → route to manual review (mirrors CONFIDENCE_REVIEW_THRESHOLD).
NEWS_CONFIDENCE_REVIEW_THRESHOLD: float = 0.5
