"""
Schemas for the request AI analysis feature (Phase 5).

RequestAnalysisResult is the instructor `response_model` for the LLM call in
app.domains.requests.analysis — it lives here (app.schemas) because
disallow_any_explicit is relaxed for schemas (pydantic's Field is Any-typed), unlike
the strict app.services scope.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RequestAnalysisResult(BaseModel):
    """Structured LLM output for a buyer-request analysis."""

    match_score: float = Field(
        ge=0.0,
        le=1.0,
        description="How well the request matches current market supply + price (0..1).",
    )
    demand_level: Literal["low", "medium", "high"] = Field(
        description="Current market demand/liquidity for the product."
    )
    recommendation: str = Field(
        max_length=600,
        description="One or two short sentences of concrete next-step advice (Russian).",
    )
