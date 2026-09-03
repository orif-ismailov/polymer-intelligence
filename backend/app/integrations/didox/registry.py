"""Didox as a state-registry channel (R6 / P7.a — Stage 1).

P7.c built the whole registry seam and shipped it stubbed, because ПЦД access
never arrived: the `GovRegistryClient` protocol, the normalized DTOs, the
append-only `registry_snapshots` table, the two pure check functions and the
operator's semi-automatic path. Didox's `/v1/utils/info/{tin}` answers with the
tax registry's own record — so this is an adapter onto that existing protocol,
not a second registry subsystem.

What it deliberately does NOT do:

  * **Invent a licence answer.** Didox carries no licence data, so
    `lookup_licenses` raises. An empty list would read as "this company holds no
    licences", which is a finding about a real business.
  * **Guess a status.** `check_gov_registry` FAILS a case on `liquidated`, so an
    unrecognised status code maps to `unknown`, never to a negative verdict. The
    registry's own wording is preserved in `raw_status`, which is what an auditor
    will look for.
  * **Turn a sandbox gap into a verdict.** A company Didox has no record of
    raises `CompanyNotFound`, which IS a `ProviderUnavailable` — every existing
    caller therefore degrades it to "no snapshot" → an `unavailable` check → the
    manual path stays open (the R1 degradation invariant), while a caller that
    cares (the registration lookup) catches the narrower type.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NoReturn

from app.integrations.didox.client import (
    DidoxClient,
    DidoxCompanyInfo,
    DidoxError,
    get_didox_client,
)
from app.integrations.didox.client import ProviderUnavailable as DidoxUnavailable
from app.integrations.gov_registry import (
    COMPANY_ACTIVE,
    COMPANY_LIQUIDATED,
    COMPANY_SUSPENDED,
    COMPANY_UNKNOWN,
    CompanySnapshot,
    LicenseSnapshot,
    ProviderUnavailable,
    VatSnapshot,
)

if TYPE_CHECKING:  # pragma: no cover
    import redis

logger = logging.getLogger(__name__)


class CompanyNotFound(ProviderUnavailable):
    """The registry answered, and it has no record of this tax id.

    A subclass of `ProviderUnavailable` on purpose: "we could not learn anything
    about this company" is what every existing caller already handles correctly,
    and the distinction only matters to the one caller that shows a form.
    """


#: Didox states its own wording; matching on it beats matching on numeric codes
#: we have no published table for.
_STATUS_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("ликвид", COMPANY_LIQUIDATED),
    ("банкрот", COMPANY_LIQUIDATED),
    ("приостан", COMPANY_SUSPENDED),
    ("бездейств", COMPANY_SUSPENDED),
    ("действ", COMPANY_ACTIVE),
)


def normalize_status(info: DidoxCompanyInfo) -> str:
    """Registry wording → our vocabulary, conservatively.

    `statusCode == 0` is the operating company in every record we have seen, but
    it is only consulted after the wording, and anything unrecognised stays
    `unknown` rather than becoming a negative verdict.
    """
    wording = (info.status_name or "").lower()
    for needle, status in _STATUS_KEYWORDS:
        if needle in wording:
            return status
    if info.status_code == 0:
        return COMPANY_ACTIVE
    return COMPANY_UNKNOWN


def to_company_snapshot(info: DidoxCompanyInfo) -> CompanySnapshot:
    return CompanySnapshot(
        inn=info.tin,
        name=info.name,
        status=normalize_status(info),
        raw_status=info.status_name,
        director=info.director,
        oked=info.oked,
        address=info.address,
        registered_at=info.registered_at,
    )


def to_vat_snapshot(info: DidoxCompanyInfo) -> VatSnapshot:
    """A missing VAT code means "not a VAT payer", which is ordinary — not every
    Uzbek company is obliged to be one, and `check_vat_status` warns rather than
    fails on it."""
    return VatSnapshot(
        registered=bool(info.vat_reg_code),
        certificate_no=info.vat_reg_code,
        valid_from=None,  # not carried by this endpoint
        raw_status=str(info.vat_reg_status) if info.vat_reg_status is not None else None,
    )


class DidoxGovRegistryClient:
    """`GovRegistryClient` backed by Didox's tax-registry lookup."""

    _NO_LICENCES = (
        "gov_registry: Didox carries no licence register — use the operator's "
        "manual check (license.gov.uz)"
    )

    def __init__(
        self,
        client: DidoxClient | None = None,
        *,
        user_key: str | None = None,
        redis_client: redis.Redis[str] | None = None,
    ) -> None:
        self._client = client if client is not None else get_didox_client()
        self._user_key = user_key
        self._redis = redis_client

    def lookup_company(self, inn: str) -> CompanySnapshot:
        return to_company_snapshot(self.fetch_info(inn))

    def lookup_vat(self, inn: str) -> VatSnapshot:
        return to_vat_snapshot(self.fetch_info(inn))

    def lookup_licenses(self, inn: str) -> list[LicenseSnapshot]:
        raise ProviderUnavailable(self._NO_LICENCES)

    # ── beyond the protocol ───────────────────────────────────────────────────

    def fetch_info(self, inn: str) -> DidoxCompanyInfo:
        """The full record, or an exception. Never a half-filled snapshot.

        Public because the registration form needs more than the protocol DTO
        carries (short name, legal form, bank requisites) and must not re-invent
        the exception translation to get it.
        """
        try:
            info = self._client.info_by_tin(inn, user_key=self._resolved_user_key())
        except DidoxUnavailable as exc:
            raise ProviderUnavailable(str(exc)) from exc
        except DidoxError as exc:
            # A 4xx is our request being wrong — still nothing learned about the
            # company, so the caller must degrade rather than draw a conclusion.
            logger.warning("didox.registry.rejected", extra={"error": str(exc)})
            raise ProviderUnavailable(f"gov_registry: didox rejected the lookup ({exc})") from exc
        if info is None:
            raise CompanyNotFound(f"gov_registry: didox has no record of {inn}")
        return info

    def _resolved_user_key(self) -> str | None:
        if self._user_key is not None:
            return self._user_key
        from app.integrations.didox.auth import service_user_key  # noqa: PLC0415 — avoids a cycle

        return service_user_key(self._redis, client=self._client)


def raise_not_found(inn: str) -> NoReturn:
    """Shared wording for callers that detect absence themselves."""
    raise CompanyNotFound(f"gov_registry: didox has no record of {inn}")
