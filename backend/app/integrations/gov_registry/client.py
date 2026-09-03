"""State-registry gateway (R6 / P7.c — T4.2).

The seam between company verification and the state registries. It ships as an
interface, three normalized DTOs and a stub — because the only official realtime
channel for a private organisation is **ПЦД**, whose access process is not
normatively formalised and whose criteria are opaque (INTEGRATIONS.md §3).

Two decisions worth keeping when the live adapter arrives:

  * **The stub RAISES; it does not answer emptily.** An empty `CompanySnapshot`
    is indistinguishable from "the registry has no record of this company",
    which would turn our missing integration into a verification finding about a
    real business. `ProviderUnavailable` maps to a check of status
    `unavailable`, and the manual path stays open — the R1 degradation invariant.
  * **`live` raises too**, naming what is missing, rather than falling back to
    the stub. A stub standing in for a state registry is the single thing this
    seam must never do.

Meanwhile the channel that works today is not a client at all: an operator reads
an open service (my.soliq.uz for the VAT register, license.gov.uz for licences)
and records the result as a `registry_snapshots` row with `source='manual'` and a
screenshot. Both paths produce the same DTO, so the check functions cannot tell
them apart — only the snapshot row's `source` can, which is exactly where that
distinction belongs.

Shape mirrors `integrations/escrow/client.py`: a typed protocol, a stub, a
factory keyed on the `gov_registry_mode` runtime setting.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.services import settings_service

logger = logging.getLogger(__name__)

MODE_STUB = "stub"
MODE_LIVE = "live"
#: P7.a — Didox's `/v1/utils/info/{tin}` reads the tax registry. It is the
#: channel ПЦД never became, and it is a third rail rather than a replacement:
#: `live` still names the missing ПЦД adapter.
MODE_DIDOX = "didox"

#: Normalized company states. `unknown` is the default rather than `active`: an
#: unstated status must never read as a positive confirmation.
COMPANY_ACTIVE = "active"
COMPANY_LIQUIDATED = "liquidated"
COMPANY_SUSPENDED = "suspended"
COMPANY_UNKNOWN = "unknown"


class ProviderUnavailable(Exception):
    """No usable registry channel for the configured mode."""


def _date(value: Any) -> datetime.date | None:  # noqa: ANN401 — untrusted JSONB/API value
    """Parse an ISO date, tolerating anything else.

    Payloads are read back from JSONB written by earlier code AND typed by
    operators, so a bad date must degrade to `None` rather than break a check.
    """
    if isinstance(value, datetime.date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.date.fromisoformat(value.strip()[:10])
    except ValueError:
        logger.warning("gov_registry.bad_date", extra={"value": value})
        return None


def _iso(value: datetime.date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text(value: Any) -> str | None:  # noqa: ANN401
    if not isinstance(value, str):
        return None
    return value.strip() or None


@dataclass(frozen=True)
class CompanySnapshot:
    """What a registry says a company IS. `status` is normalized; `raw_status`
    keeps the registry's own wording, which is what an auditor will look for."""

    inn: str
    name: str | None = None
    status: str = COMPANY_UNKNOWN
    raw_status: str | None = None
    director: str | None = None
    oked: str | None = None
    address: str | None = None
    registered_at: datetime.date | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "inn": self.inn,
            "name": self.name,
            "status": self.status,
            "raw_status": self.raw_status,
            "director": self.director,
            "oked": self.oked,
            "address": self.address,
            "registered_at": _iso(self.registered_at),
        }


def company_from_payload(payload: dict[str, Any]) -> CompanySnapshot:
    return CompanySnapshot(
        inn=str(payload.get("inn") or ""),
        name=_text(payload.get("name")),
        status=_text(payload.get("status")) or COMPANY_UNKNOWN,
        raw_status=_text(payload.get("raw_status")),
        director=_text(payload.get("director")),
        oked=_text(payload.get("oked")),
        address=_text(payload.get("address")),
        registered_at=_date(payload.get("registered_at")),
    )


@dataclass(frozen=True)
class LicenseSnapshot:
    """One licence as the registry lists it.

    `regime` uses OUR `RegulationRegime` vocabulary (P5) where it can be mapped:
    the four Uzbek chemistry regimes each have their own licensor, and a licence
    that cannot be attributed to a regime cannot satisfy a publication gate.
    """

    regime: str | None = None
    number: str | None = None
    issuer: str | None = None
    issued_at: datetime.date | None = None
    expires_at: datetime.date | None = None
    status: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "number": self.number,
            "issuer": self.issuer,
            "issued_at": _iso(self.issued_at),
            "expires_at": _iso(self.expires_at),
            "status": self.status,
        }


def license_from_payload(payload: dict[str, Any]) -> LicenseSnapshot:
    return LicenseSnapshot(
        regime=_text(payload.get("regime")),
        number=_text(payload.get("number")),
        issuer=_text(payload.get("issuer")),
        issued_at=_date(payload.get("issued_at")),
        expires_at=_date(payload.get("expires_at")),
        status=_text(payload.get("status")),
    )


def licenses_payload(items: list[LicenseSnapshot]) -> dict[str, Any]:
    """A list of licences wrapped in an object — `registry_snapshots.payload` is
    JSONB of an object, and a bare array would leave nowhere to add context."""
    return {"licenses": [item.as_payload() for item in items]}


def licenses_from_payload(payload: dict[str, Any]) -> list[LicenseSnapshot]:
    raw = payload.get("licenses")
    if not isinstance(raw, list):
        return []
    return [license_from_payload(item) for item in raw if isinstance(item, dict)]


@dataclass(frozen=True)
class VatSnapshot:
    """VAT-register status.

    `registered=False` is NOT a problem in itself — not every Uzbek company is
    obliged to be a VAT payer, which is why `check_vat_status` treats it as a
    warning rather than a failure.
    """

    registered: bool = False
    certificate_no: str | None = None
    valid_from: datetime.date | None = None
    raw_status: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        return {
            "registered": self.registered,
            "certificate_no": self.certificate_no,
            "valid_from": _iso(self.valid_from),
            "raw_status": self.raw_status,
        }


def vat_from_payload(payload: dict[str, Any]) -> VatSnapshot:
    return VatSnapshot(
        registered=bool(payload.get("registered")),
        certificate_no=_text(payload.get("certificate_no")),
        valid_from=_date(payload.get("valid_from")),
        raw_status=_text(payload.get("raw_status")),
    )


@runtime_checkable
class GovRegistryClient(Protocol):
    """What company verification needs from a state registry.

    Every method either returns a snapshot or raises `ProviderUnavailable`.
    Nothing here decides anything: the pure functions in `verification_checks`
    turn a snapshot into a verdict, so the same snapshot from ПЦД and from an
    operator's transcription is judged by identical code.
    """

    def lookup_company(self, inn: str) -> CompanySnapshot:
        """Registry record for a tax id (ЕГРПО-equivalent)."""
        ...

    def lookup_licenses(self, inn: str) -> list[LicenseSnapshot]:
        """Licences issued to a tax id (КИС «Лицензия»-equivalent)."""
        ...

    def lookup_vat(self, inn: str) -> VatSnapshot:
        """VAT-certificate status for a tax id (my.soliq.uz-equivalent)."""
        ...


class StubGovRegistryClient:
    """The honest absence of a channel.

    Raises rather than returning empty snapshots — see the module docstring. The
    caller records the check as `unavailable`, and the manual verification path
    (staff + documents + R3 E-IMZO, still the strongest signal we have: a
    signature proves control of the company and carries the registry-certified
    INN, name and director) continues to work.
    """

    _WHY = "gov_registry: no channel configured (ПЦД access pending)"

    def lookup_company(self, inn: str) -> CompanySnapshot:
        raise ProviderUnavailable(self._WHY)

    def lookup_licenses(self, inn: str) -> list[LicenseSnapshot]:
        raise ProviderUnavailable(self._WHY)

    def lookup_vat(self, inn: str) -> VatSnapshot:
        raise ProviderUnavailable(self._WHY)


def current_mode() -> str:
    """The configured rail, read from `GOV_REGISTRY_MODE` in `.env`.

    Took a `Session` until the switches moved out of `app_settings`; it
    never queried anything, and a parameter implying a lookup that does
    not happen is the sort of thing that gets copied forward.
    """
    return str(settings_service.get("gov_registry_mode"))


def get_gov_registry_client(db: Any) -> GovRegistryClient:  # noqa: ANN401
    """The client for the configured rail.

    `live` raises: the ПЦД adapter does not exist yet, and answering with the
    stub instead would let an operator believe a state registry confirmed
    something when nothing did.
    """
    mode = current_mode()
    if mode == MODE_STUB:
        return StubGovRegistryClient()
    if mode == MODE_DIDOX:
        # Imported here rather than at module scope: `integrations.didox.registry`
        # imports this module for the protocol and the DTOs, so a top-level
        # import would be a cycle.
        from app.integrations.didox.registry import DidoxGovRegistryClient  # noqa: PLC0415

        return DidoxGovRegistryClient()
    if mode == MODE_LIVE:
        raise ProviderUnavailable(
            "gov_registry: live mode has no adapter yet (needs ПЦД access) — "
            "set gov_registry_mode=stub"
        )
    raise ProviderUnavailable(f"gov_registry: unknown mode {mode!r}")
