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

import dataclasses
import datetime
import json
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

#: One Didox registry record per tax id, shared by every consumer in every process.
INFO_CACHE_KEY = "didox:info:{tin}"

#: A day. The registration prefill, the `gov_registry` check and the `vat_status`
#: check all read the same `/v1/utils/info/{tin}` record, usually minutes apart;
#: without this they asked Didox for it separately (eight calls for one company on
#: 23.09.2026, most of them timeouts). A day is comfortably safe for the facts
#: judged here — liquidating a company in Uzbekistan takes more than a month.
INFO_CACHE_TTL_SECONDS = 24 * 60 * 60


def _dump_info(info: DidoxCompanyInfo) -> str:
    data = dataclasses.asdict(info)
    if isinstance(info.registered_at, datetime.date):
        data["registered_at"] = info.registered_at.isoformat()
    return json.dumps(data, ensure_ascii=False)


def _load_info(raw: str) -> DidoxCompanyInfo:
    data = json.loads(raw)
    known = {f.name for f in dataclasses.fields(DidoxCompanyInfo)}
    data = {k: v for k, v in data.items() if k in known}
    if data.get("registered_at"):
        data["registered_at"] = datetime.date.fromisoformat(data["registered_at"])
    return DidoxCompanyInfo(**data)


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


#: Short codes, matched on the WHOLE value after stripping punctuation and case.
#: Separate from the keyword table because these are too short to be substrings:
#: «АЖ» inside a longer word, or «ХК» inside an address, would place a company
#: in a legal form nobody claimed.
_LEGAL_FORM_ABBREVIATIONS: dict[str, str] = {
    "ООО": "ООО", "МЧЖ": "ООО", "MCHJ": "ООО", "OOO": "ООО", "LLC": "ООО",
    "ЧП": "ЧП", "ХК": "ЧП", "XK": "ЧП",
    "АО": "АО", "АЖ": "АО", "AJ": "АО", "JSC": "АО",
    "СП": "СП", "ҚК": "СП", "QK": "СП",
    "ИП": "ИП", "ЯТТ": "ИП", "YATT": "ИП",
    "ГУП": "ГУП", "ДУК": "ГУП", "DUK": "ГУП",
}

#: Distinctive stems, checked in order against the lower-cased wording.
#:
#: Two traps, both of which a mapping written from the spelt-out names alone
#: walks into. Didox ABBREVIATES — the one captured record says «Общество с огр.
#: ответствен.», so «огранич» never matches it — and three of the six forms end
#: in «предприятие», so only the leading stem may decide between them. For the
#: same reason the LLC rule may not match a bare «общество»: «Акционерное
#: общество» is a different form and would be swallowed by it.
_LEGAL_FORM_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("общество с огр", "ООО"),
    ("огранич", "ООО"),
    ("cheklangan", "ООО"),
    ("чекланган", "ООО"),
    ("акционер", "АО"),
    ("aksiyador", "АО"),
    ("акциядор", "АО"),
    ("совместн", "СП"),
    ("qo'shma", "СП"),
    ("qo‘shma", "СП"),
    ("qoshma", "СП"),
    ("қўшма", "СП"),
    ("индивидуальн", "ИП"),
    ("yakka tartib", "ИП"),
    ("якка тартиб", "ИП"),
    ("унитар", "ГУП"),
    ("unitar", "ГУП"),
    ("частн", "ЧП"),
    ("xususiy", "ЧП"),
    ("хусусий", "ЧП"),
)


def normalize_legal_form(value: str | None) -> str | None:
    """Registry wording → the code the registration select offers, or unchanged.

    `companies.legal_form` is free text and the portal's «Форма собственности»
    appends any value it does not recognise as an extra option, labelled with its
    raw string. Didox states the form in its own words, so without this the
    prefill produced a select listing the same legal form twice — «Общество с
    ограниченной ответственностью» (ours) beside «Общество с огр. ответствен.»
    (theirs) — and auto-selected the registry's spelling, taking the stored value
    off the vocabulary with it.

    Unrecognised wording is returned **unchanged**, never guessed. That branch is
    load-bearing: `СП ООО` exists in real rows, names two forms and belongs to
    neither, and collapsing it into one would rewrite a company's legal form on
    its next save. The portal's append-an-option branch is where such a value is
    meant to land.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    exact = _LEGAL_FORM_ABBREVIATIONS.get(text.upper().replace(".", "").replace('"', "").strip())
    if exact is not None:
        return exact

    lowered = text.lower()
    for needle, code in _LEGAL_FORM_KEYWORDS:
        if needle in lowered:
            return code
    return text


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

        Read through a day-long Redis cache (`INFO_CACHE_KEY`), so the prefill and
        both registry checks cost Didox ONE call between them. Only a FOUND record
        is cached — a company registered this morning may reach the registry this
        afternoon, and caching its absence would hide it for a day. Redis is an
        optimisation only: any error there is a miss, never a failed lookup.
        """
        cached = self._cached(inn)
        if cached is not None:
            return cached
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
        self._remember(inn, info)
        return info

    def _cached(self, inn: str) -> DidoxCompanyInfo | None:
        if self._redis is None:
            return None
        try:
            raw = self._redis.get(INFO_CACHE_KEY.format(tin=inn))
            return _load_info(raw) if raw else None
        except Exception as exc:  # noqa: BLE001 — a cache must never fail a lookup
            logger.warning("didox.info_cache.read_failed", extra={"error": str(exc)})
            return None

    def _remember(self, inn: str, info: DidoxCompanyInfo) -> None:
        if self._redis is None:
            return
        try:
            self._redis.setex(
                INFO_CACHE_KEY.format(tin=inn), INFO_CACHE_TTL_SECONDS, _dump_info(info)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("didox.info_cache.write_failed", extra={"error": str(exc)})

    def _resolved_user_key(self) -> str | None:
        if self._user_key is not None:
            return self._user_key
        from app.integrations.didox.auth import service_user_key  # noqa: PLC0415 — avoids a cycle

        return service_user_key(self._redis, client=self._client)


def raise_not_found(inn: str) -> NoReturn:
    """Shared wording for callers that detect absence themselves."""
    raise CompanyNotFound(f"gov_registry: didox has no record of {inn}")
