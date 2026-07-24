"""
CBU RUz official exchange-rate adapter.

Fetches the daily rate table from:
    https://cbu.uz/ru/arkhiv-kursov-valyut/json/

Response is a JSON array where each element has:
    Ccy   — ISO 4217 currency code (e.g. "USD", "CNY", "RUB")
    Rate  — rate in UZS per 1 unit of Ccy (decimal string)
    Date  — DD.MM.YYYY date string (e.g. "21.07.2026"); ISO is accepted as a fallback

Security:
  T-02-15: Strict Decimal parsing with try/except → skips any malformed Rate;
           never uses float() or eval() for money values.
  T-02-16: All SQL uses bound parameters via ORM / fx_service.
  All outbound HTTP goes through http_client.fetch_url (SSRF guard).

Registration:
  The adapter instance is registered under type_name="cbu_rates" at module
  import time (DEC-source-adapter-registry). Importing this module is sufficient.
"""

from __future__ import annotations

import datetime
import decimal
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.ingest.base import RawItemDraft, TestResult
from app.ingest.registry import register_adapter

if TYPE_CHECKING:
    from app.models.sources import Source

logger = logging.getLogger(__name__)

# CBU public JSON endpoint (official, no auth required)
_CBU_DEFAULT_URL = "https://cbu.uz/ru/arkhiv-kursov-valyut/json/"


def _parse_cbu_date(raw_date: object) -> datetime.date | None:
    """Parse a CBU `Date` value. CBU returns DD.MM.YYYY (e.g. '21.07.2026'); we also
    accept ISO YYYY-MM-DD as a fallback in case the API format ever changes.

    Returns None when the value can't be parsed (caller skips the row). The previous
    code assumed ISO only, so every real CBU row was skipped and fx_rates stayed empty.
    """
    s = str(raw_date).strip()
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s, "%d.%m.%Y").date()
    except (ValueError, TypeError):
        pass
    try:
        return datetime.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@dataclass
class CbuRateRow:
    """A single parsed rate row from the CBU JSON response.

    Fields:
    - rate_date: observation date (YYYY-MM-DD)
    - ccy: ISO 4217 currency code (3 chars, e.g. "USD")
    - rate: UZS per 1 unit of ccy as Decimal (never float — T-02-15)
    """

    rate_date: datetime.date
    ccy: str
    rate: decimal.Decimal


class CbuRatesConfig(BaseModel):
    """Config schema for the cbu_rates adapter.

    Fields exposed in the admin add-source wizard (Phase 4).
    """

    endpoint_url: str = _CBU_DEFAULT_URL
    ccy_allowlist: list[str] = []  # empty = accept all currencies


class CbuRatesAdapter:
    """SourceAdapter for the official CBU RUz exchange-rate JSON API.

    type_name = "cbu_rates" (registered in the global adapter registry on import)

    fetch(source) returns RawItemDraft list only for orchestration compatibility;
    the actual upsert into fx_rates is performed by the fetch_cbu_rates Celery
    task which calls the adapter and then calls fx_service.upsert_fx_rates directly
    (preferred for tabular sources where raw_items dedup is not needed).

    test(config) returns up to 10 sample rate rows from the live endpoint.
    """

    type_name: str = "cbu_rates"
    config_schema: type[BaseModel] = CbuRatesConfig

    def _parse_cbu_json(self, body: str) -> list[CbuRateRow]:
        """Parse the raw CBU JSON response body into CbuRateRow objects.

        Skips any row where:
        - Rate is not parseable as Decimal (T-02-15: malformed number)
        - Date is not parseable as YYYY-MM-DD
        - Ccy is missing or empty

        Args:
            body: Raw JSON string from the CBU endpoint.

        Returns:
            List of CbuRateRow objects for well-formed rows.
        """
        try:
            items = json.loads(body)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("cbu_rates.parse_error", extra={"error": str(exc)})
            return []

        if not isinstance(items, list):
            logger.error("cbu_rates.unexpected_format", extra={"type": type(items).__name__})
            return []

        rows: list[CbuRateRow] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            ccy = str(item.get("Ccy", "")).strip()
            if len(ccy) != 3:
                logger.debug("cbu_rates.skip_invalid_ccy", extra={"ccy": ccy})
                continue

            raw_rate = item.get("Rate", "")
            raw_date = item.get("Date", "")

            # Strict Decimal parsing — never use float() (T-02-15)
            try:
                rate = decimal.Decimal(str(raw_rate).strip())
                # Reject NaN and Inf (T-02-15)
                if not rate.is_finite() or rate <= 0:
                    logger.warning(
                        "cbu_rates.skip_nonfinite_rate",
                        extra={"ccy": ccy, "rate": str(raw_rate)},
                    )
                    continue
            except (decimal.InvalidOperation, ValueError, TypeError):
                logger.warning(
                    "cbu_rates.skip_malformed_rate",
                    extra={"ccy": ccy, "raw_rate": str(raw_rate)},
                )
                continue

            rate_date = _parse_cbu_date(raw_date)
            if rate_date is None:
                logger.warning(
                    "cbu_rates.skip_malformed_date",
                    extra={"ccy": ccy, "raw_date": str(raw_date)},
                )
                continue

            rows.append(CbuRateRow(rate_date=rate_date, ccy=ccy, rate=rate))

        logger.info("cbu_rates.parsed", extra={"count": len(rows)})
        return rows

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Fetch CBU rates and return as RawItemDraft for orchestration.

        Reads endpoint_url and ccy_allowlist from source.config.
        ccy_allowlist is an optional list of ISO 4217 codes (e.g. ["USD", "CNY"]);
        when non-empty only those currencies are returned (WR-02: previously the
        field was declared in CbuRatesConfig but never enforced here).

        Note: The fetch_cbu_rates Celery task calls the adapter directly and
        upserts via fx_service rather than going through the raw_items pipeline.
        This method is provided for protocol compliance.
        """
        from app.ingest.http_client import fetch_url  # noqa: PLC0415

        config = source.config or {}
        endpoint_url = str(config.get("endpoint_url", _CBU_DEFAULT_URL))
        # WR-02: enforce ccy_allowlist — empty list means accept all currencies
        allowlist: list[str] = [
            str(c).upper() for c in (config.get("ccy_allowlist") or [])
        ]

        response = await fetch_url(endpoint_url)
        body = response.text

        rows = self._parse_cbu_json(body)

        # Apply currency allowlist filter when configured
        if allowlist:
            rows = [r for r in rows if r.ccy in allowlist]

        # Return rows as RawItemDraft for protocol compliance
        return [
            RawItemDraft(
                external_id=f"{row.rate_date.isoformat()}:{row.ccy}",
                content=None,
                payload={"rate_date": row.rate_date.isoformat(), "ccy": row.ccy, "rate": str(row.rate)},
                event_at=None,
            )
            for row in rows
        ]

    async def test(self, config: dict[str, object]) -> TestResult:
        """Test the CBU endpoint and return up to 10 sample rate rows."""
        from app.ingest.http_client import fetch_url  # noqa: PLC0415

        endpoint_url = str(config.get("endpoint_url", _CBU_DEFAULT_URL))

        try:
            response = await fetch_url(endpoint_url)
            rows = self._parse_cbu_json(response.text)

            sample: list[dict[str, object]] = [
                {"rate_date": r.rate_date.isoformat(), "ccy": r.ccy, "rate": str(r.rate)}
                for r in rows[:10]
            ]
            return TestResult(ok=True, sample_rows=sample)

        except Exception as exc:
            logger.error("cbu_rates.test_error", extra={"error": str(exc)})
            return TestResult(ok=False, error=str(exc))


# ── Self-register on import ────────────────────────────────────────────────────
# This line executes when the module is first imported, adding "cbu_rates" to
# the global adapter registry. The Celery task and admin source-types endpoint
# look up the adapter by type_name at runtime.
_adapter_instance = CbuRatesAdapter()
register_adapter(_adapter_instance)
