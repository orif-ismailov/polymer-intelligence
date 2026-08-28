"""Didox partner-API gateway (R6 / P7.a).

Didox (ООО «DIDOX TECH», ИНН 310529901) is Uzbekistan's largest private EDI
operator. Stage 1 uses one endpoint of it — `GET /v1/utils/info/{TinOrPinfl}`,
the tax registry's own record of a company — to fill the registration form and
to feed the P7.c verification checks. The rest of the ported surface (documents,
DSVS, catalogs) lands with the signing rails.

Shape is `integrations/eimzo/client.py` verbatim: injectable transport, a circuit
breaker, one `integration_call_log` row per call on an isolated session, and the
split that matters —

  * **5xx / transport / open breaker → `ProviderUnavailable`** (an outage; the
    caller degrades, nothing is decided about the company);
  * **4xx → `DidoxError`** (our request was wrong; it does NOT trip the breaker),
    except **401/403, which are ALSO an outage**: production refuses this
    endpoint without a `user-key` (`Token expired` with none, `Invalid user key`
    with a stale one), and that is a statement about our configuration, never
    about the company being looked up.

The auth model is two independent tokens, both documented in the skill
(`~/.claude/skills/didox`):

    Partner-Authorization: <PARTNER_TOKEN>   # integrator identity — server-side SECRET
    user-key: <USER_TOKEN>                   # the acting user/company — UUID, TTL 360 min

`Partner-Authorization` rides on **every** request including auth. The user-key
cannot be minted server-side for an arbitrary company (it needs that company's
E-IMZO key), which is why `auth.py` mints one for OUR OWN service account and
why its absence degrades rather than fails.

One behaviour no reading of the docs would have revealed, recorded live against
`testapi3` on 2026-08-15 and pinned by the tests: **"no such company" is a 200
with an envelope full of nulls**, not a 404. `DidoxCompanyInfo.from_payload`
returns `None` for it — an empty DTO would put a blank legal name in a form and
an "unknown" registry status on a verification check.
"""

from __future__ import annotations

import datetime
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.integrations.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

_PROVIDER = "didox"
_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)

TEST_BASE_URL = "https://testapi3.didox.uz"
PROD_BASE_URL = "https://api-partners.didox.uz"


class ProviderUnavailable(Exception):
    """Didox is unreachable/slow/5xx, the breaker is open, or our auth is unusable."""


class DidoxError(Exception):
    """Didox answered 4xx: our request was wrong.

    `trace_id` is the `x-trace-id` echoed back in `errorDetails.id` — quote it to
    Didox support. `description` is their own "what to do about it" text, present
    only for errors they have an explanation for.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        trace_id: str | None = None,
        description: str | None = None,
        context: Any = None,  # noqa: ANN401 — untrusted provider JSON
    ) -> None:
        super().__init__(f"didox {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.trace_id = trace_id
        self.description = description
        self.context = context

    @property
    def offer_not_signed(self) -> bool:
        """The company has never signed Didox's public offer.

        A one-time onboarding step (`GET /v1/newoffer/base64` → `/offer/create` →
        `/offer/sign`) that fails the FIRST document send and nothing before it —
        reads/creates succeed, so nothing warns you earlier. Worth a named flag
        rather than a regex at the call site, because the message is Russian and
        theirs to reword.
        """
        if isinstance(self.context, dict) and self.context.get("offer") == "required":
            return True
        # What they ACTUALLY send (verified 21.08.2026, `PUT /{id}/send`): a
        # 422 whose Russian message ends «...необходимо подписать условия
        # публичной оферты на сайте didox.uz». There is no code, no context
        # object and no field — the prose is the whole signal.
        return "публичной оферты" in (self.message or "")


def _text(value: Any) -> str | None:  # noqa: ANN401 — untrusted provider JSON
    """Trim to None. Didox pads several fields with trailing spaces, and an
    address with a ragged tail is visible the moment it lands in a form field."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _int(value: Any) -> int | None:  # noqa: ANN401
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _ru_date(value: Any) -> datetime.date | None:  # noqa: ANN401
    """Parse Didox's `dd.mm.yyyy`, tolerating ISO and anything else.

    Every date we store is a real `date`; a string here would reach
    `companies.registration_date` as a type error at insert time, i.e. at the
    worst possible moment.
    """
    text = _text(value)
    if text is None:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    logger.warning("didox.bad_date", extra={"value": text})
    return None


@dataclass(frozen=True)
class DidoxCompanyInfo:
    """The registry record behind `/v1/utils/info/{tin}`.

    Richer than `gov_registry.CompanySnapshot` on purpose: the snapshot is what
    the verification checks judge, while this also carries what a registration
    form wants to prefill (short name, legal form, bank requisites, VAT code).
    `registry.py` narrows it to the protocol DTOs.
    """

    tin: str
    name: str | None = None
    short_name: str | None = None
    legal_form: str | None = None
    address: str | None = None
    oked: str | None = None
    registered_at: datetime.date | None = None
    status_code: int | None = None
    status_name: str | None = None
    director: str | None = None
    director_pinfl: str | None = None
    director_tin: str | None = None
    accountant: str | None = None
    bank_mfo: str | None = None
    bank_account: str | None = None
    vat_reg_code: str | None = None
    vat_reg_status: int | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> DidoxCompanyInfo | None:  # noqa: ANN401
        """Parse a lookup response, or `None` when the registry has no record.

        Didox signals "not found" with HTTP 200 and an envelope whose every
        field is null or "" — so absence is detected here, once, rather than by
        each caller noticing an empty name.
        """
        if not isinstance(payload, dict):
            return None
        tin = _text(payload.get("tin"))
        name = _text(payload.get("name")) or _text(payload.get("fullName"))
        if tin is None and name is None:
            return None
        return cls(
            tin=tin or "",
            name=name,
            short_name=_text(payload.get("shortName")) or _text(payload.get("shortname")),
            legal_form=_text(payload.get("na1Name")),
            address=_text(payload.get("address")),
            oked=_text(payload.get("oked")),
            registered_at=_ru_date(payload.get("regDate")),
            status_code=_int(payload.get("statusCode")),
            status_name=_text(payload.get("statusName")),
            director=_text(payload.get("director")),
            director_pinfl=_text(payload.get("directorPinfl")),
            director_tin=_text(payload.get("directorTin")),
            accountant=_text(payload.get("accountant")),
            bank_mfo=_text(payload.get("mfo")) or _text(payload.get("bankCode")),
            bank_account=_text(payload.get("account")) or _text(payload.get("bankAccount")),
            vat_reg_code=_text(payload.get("VATRegCode")),
            vat_reg_status=_int(payload.get("VATRegStatus")),
        )


@dataclass(frozen=True)
class DidoxCreatedDocument:
    """What `POST /v1/documents/{docType}/create/{locale}` hands back.

    **`didox_id` and `didox_contract_id` are DIFFERENT identifiers** — verified on
    the live contour: a 007 create returned `_id = 8ca023ec…` (32 hex) and
    `document_json.contractid = 6a857945…` (24 hex). `didox_id` addresses the
    document in every later call; `didox_contract_id` is what an ЭСФ carries in
    its service field `didoxcontractid` to point at its договор.

    Neither is the `contractId` that `GET /v1/documents/contract/{id}/info` takes —
    that endpoint rejects both with "должно быть целым числом", so its id is the
    my.soliq.uz-registered contract, a different namespace again.
    """

    didox_id: str
    didox_contract_id: str | None
    document_json: dict[str, Any]


@dataclass(frozen=True)
class DidoxDocumentView:
    """`GET /v1/documents/{id}?owner=…` — the document plus its signing payloads."""

    json_payload: dict[str, Any]
    to_sign: str | None
    status: int | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class DidoxSignResult:
    """A sign/reject/cancel outcome.

    `warning` is non-None when the tax committee accepted the document WITH
    remarks (`warningDetails` alongside a 200). That is a success carrying a note,
    not a failure — log it, do not raise it.
    """

    ok: bool
    warning: dict[str, Any] | None = None


@dataclass(frozen=True)
class DidoxVatStatus:
    """VAT registration of one party, AS AT a date and for one role."""

    code: str | None
    status: int | None
    status_code: str | None


@dataclass(frozen=True)
class DidoxProductClass:
    """One ИКПУ row: the code, its packages, and the ЭСФ `Origin`."""

    class_code: str
    name: str | None
    packages: list[tuple[str, str]]
    origin_id: int | None
    origin_name: str | None
    use_package: bool


class DidoxClient:
    """Thin, testable client for the Didox partner API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        partner_token: str | None = None,
        user_key: str | None = None,
        client_factory: Callable[[], httpx.Client] | None = None,
        breaker: CircuitBreaker | None = None,
        session_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if base_url is None or partner_token is None:
            from app.core.config import settings  # noqa: PLC0415 — lazy: import-safe module

            base_url = base_url if base_url is not None else settings.DIDOX_BASE_URL
            partner_token = (
                partner_token if partner_token is not None else settings.DIDOX_PARTNER_TOKEN
            )
        self._base_url = base_url.rstrip("/")
        self._partner_token = partner_token
        self._user_key = user_key
        self._client_factory = client_factory or (lambda: httpx.Client(timeout=_TIMEOUT))
        self._breaker = breaker or CircuitBreaker()
        self._session_factory = session_factory
        self._clock = clock

    # ── public surface (Stage 1) ──────────────────────────────────────────────

    def info_by_tin(self, tin: str, *, user_key: str | None = None) -> DidoxCompanyInfo | None:
        """Registry record for an INN/ПИНФЛ, or `None` when there is no record."""
        body = self._request("GET", f"/v1/utils/info/{tin}", "info_by_tin", user_key=user_key)
        return DidoxCompanyInfo.from_payload(body)

    def banks(self, *, user_key: str | None = None) -> Any:  # noqa: ANN401
        """МФО classifier. Needs no user-key on either contour."""
        return self._request("GET", "/v1/banks/all", "banks", user_key=user_key)

    def measures(self, *, user_key: str | None = None) -> Any:  # noqa: ANN401
        """Units of measure (`packagecode`/`packagename` for document lines)."""
        return self._request("GET", "/v1/measures/all", "measures", user_key=user_key)

    def auth_by_password(self, tax_id: str, password: str, locale: str = "ru") -> str:
        """Mint a `user-key` by password → the token (a UUID, TTL 360 minutes).

        **Never call this in a loop.** The lockout ladder is 3 wrong/min → 10 min,
        10 → 24 h, 25 → PERMANENT (`reference/03-login.md`); `auth.py` enforces
        one attempt per cache miss.
        """
        body = self._request(
            "POST",
            f"/v1/auth/{tax_id}/password/{locale}",
            "auth_by_password",
            json_body={"password": password},
        )
        token = (body or {}).get("token") if isinstance(body, dict) else None
        if not token:
            raise ProviderUnavailable("didox: auth response carried no token")
        return str(token)

    # ── dsvs: timestamp + join (Stage 2) ──────────────────────────────────────

    def timestamp(self, pkcs7_64: str, signature_hex: str, *, user_key: str | None = None) -> str:
        """Attach a TSA timestamp to a fresh PKCS#7 → `timeStampTokenB64`.

        **Mandatory after every `create_pkcs7`.** A bare `pkcs7_64` is rejected by
        every endpoint that takes a `signature`. Needs only the partner token, so
        this leg stays server-side and the token never reaches a browser.

        Note the asymmetry in the field names — `pkcs7` snake-free, `signatureHex`
        camelCase — which is theirs, not a typo here.
        """
        body = self._request(
            "POST",
            "/v1/dsvs/timestamp",
            "timestamp",
            user_key=user_key,
            json_body={"pkcs7": pkcs7_64, "signatureHex": signature_hex},
        )
        token = (body or {}).get("timeStampTokenB64") if isinstance(body, dict) else None
        if not token:
            raise ProviderUnavailable("didox: timestamp response carried no token")
        return str(token)

    def join_signatures(
        self, signature1: str, signature2: str, *, user_key: str | None = None
    ) -> str:
        """Merge the sender's signature with ours (incoming documents only).

        Order matters: `signature1` is THEIRS (the `toSign` off the document),
        `signature2` is ours. Swapped, it produces a PKCS#7 that is rejected
        downstream rather than an error here.
        """
        body = self._request(
            "POST",
            "/v1/dsvs/signature/join",
            "join_signatures",
            user_key=user_key,
            json_body={"signature1": signature1, "signature2": signature2},
        )
        joined = (body or {}).get("pkcs7B64") if isinstance(body, dict) else None
        if not joined:
            raise ProviderUnavailable("didox: join response carried no pkcs7B64")
        return str(joined)

    # ── documents (Stage 2) ───────────────────────────────────────────────────

    def create_document(
        self,
        doc_type: str,
        payload: dict[str, Any],
        *,
        locale: str = "ru",
        user_key: str | None = None,
    ) -> DidoxCreatedDocument:
        """Create a draft. `payload` is PascalCase; the echo comes back lowercased."""
        body = self._request(
            "POST",
            f"/v1/documents/{doc_type}/create/{locale}",
            "create_document",
            user_key=user_key,
            json_body=payload,
        )
        envelope = body if isinstance(body, dict) else {}
        didox_id = _text(envelope.get("_id"))
        if not didox_id:
            raise ProviderUnavailable("didox: create response carried no _id")
        document_json = (envelope.get("pending_document") or {}).get("document_json") or {}
        if not isinstance(document_json, dict):
            document_json = {}
        return DidoxCreatedDocument(
            didox_id=didox_id,
            didox_contract_id=_text(document_json.get("contractid")),
            document_json=document_json,
        )

    def get_document(
        self, didox_id: str, *, owner: int = 1, user_key: str | None = None
    ) -> DidoxDocumentView:
        """Detail view. `owner=1` outgoing (ours), `owner=0` incoming (theirs).

        `int(owner)` is not cosmetic: `bool` IS an `int` to the type checker, so
        `owner=True` passes mypy and then goes over the wire as `owner=true`,
        which Didox answers with a bare 500. Coerced here so the trap cannot be
        re-sprung by a caller.
        """
        body = self._request(
            "GET",
            f"/v1/documents/{didox_id}",
            "get_document",
            user_key=user_key,
            params={"owner": int(owner)},
        )
        data = (body or {}).get("data") if isinstance(body, dict) else None
        data = data if isinstance(data, dict) else {}
        json_payload = data.get("json")
        document = data.get("document")
        return DidoxDocumentView(
            json_payload=json_payload if isinstance(json_payload, dict) else {},
            to_sign=_text(data.get("toSign")),
            status=_int((document or {}).get("status")) if isinstance(document, dict) else None,
            raw=data,
        )

    def document_base64(self, didox_id: str, *, user_key: str | None = None) -> str:
        """The bytes an INCOMING document is signed over (before the join)."""
        return self._base64_body(
            f"/v1/documents/{didox_id}/documentBase64", "document_base64", user_key
        )

    def _base64_body(self, path: str, operation: str, user_key: str | None) -> str:
        """Read an endpoint that answers with BARE base64 text, not JSON.

        `/v1/newoffer/base64` and `/documentBase64` return the payload as a plain
        body — no envelope, no quotes. Routing them through `resp.json()` fails,
        and the failure is indistinguishable from an outage at the call site: the
        offer step reported `didox_unavailable` while Didox had answered 200 with
        a perfectly good PDF. Found by running it, not by a mock.

        Some deployments DO wrap it (`{"data": "…"}`), so both shapes are accepted.
        """
        raw = self._request("GET", path, operation, user_key=user_key, raw=True)
        text = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else ""
        if text.startswith("{"):
            try:
                envelope = json.loads(text)
            except ValueError:
                envelope = None
            if isinstance(envelope, dict):
                text = str(envelope.get("data") or "")
        text = text.strip('"')
        if not text:
            raise ProviderUnavailable(f"didox: {operation} carried nothing")
        return text

    def to_sign(
        self, didox_id: str, action: str, *, comment: str = "", user_key: str | None = None
    ) -> Any:  # noqa: ANN401 — the shape genuinely varies; see below
        """Data to sign for an ACTION (accept/reject/cancel/ТТН moves).

        Returns whatever Didox returns: `data` is sometimes an object to sign,
        sometimes an already-built base64 signature string, and sometimes empty —
        it depends on the (action, docType) pair. Branch on the runtime type at
        the call site; normalising it here would invent a shape.
        """
        body = self._request(
            "POST",
            f"/v1/documents/{didox_id}/tosign",
            "to_sign",
            user_key=user_key,
            json_body={"action": action, "comment": comment},
        )
        return (body or {}).get("data") if isinstance(body, dict) else None

    def sign_document(
        self, didox_id: str, signature: str, *, user_key: str | None = None
    ) -> DidoxSignResult:
        """Sign — which IS sending. The counterparty sees it the moment this returns."""
        body = self._request(
            "POST",
            f"/v1/documents/{didox_id}/sign",
            "sign_document",
            user_key=user_key,
            json_body={"signature": signature},
        )
        return self._sign_result(body)

    def send_document(
        self, didox_id: str, signature: str, *, user_key: str | None = None
    ) -> DidoxSignResult:
        """`PUT /{id}/send` — kept, but NOT the door a «Договор НК» uses.

        Recorded live: on 21.08, with the public offer unsigned, `POST /{id}/sign`
        answered 500 `Undefined variable $isDraft` and this route gave the only
        actionable error in the chain. Once the offer was signed (25.08) the two
        swapped places — `/sign` began validating signatures properly and this
        route answers «Неподдерживаемый тип документа» for a 007. So the 500 was a
        symptom of the unsigned offer; this stays for the document types that do
        use it, and `submit_signature` no longer routes through it.
        """
        body = self._request(
            "PUT",
            f"/v1/documents/{didox_id}/send",
            "send_document",
            user_key=user_key,
            json_body={"signature": signature},
        )
        return self._sign_result(body)

    def reject_document(
        self, didox_id: str, signature: str, comment: str, *, user_key: str | None = None
    ) -> DidoxSignResult:
        """Refuse an incoming document.

        `comment` must be BYTE-IDENTICAL to the one passed to `to_sign`, or the
        call fails — so callers pass the same string object to both.
        """
        body = self._request(
            "POST",
            f"/v1/documents/{didox_id}/reject",
            "reject_document",
            user_key=user_key,
            json_body={"signature": signature, "comment": comment},
        )
        return self._sign_result(body)

    def cancel_document(
        self, didox_id: str, signature: str, *, user_key: str | None = None
    ) -> DidoxSignResult:
        """Cancel a document we already sent."""
        body = self._request(
            "POST",
            f"/v1/documents/{didox_id}/delete",
            "cancel_document",
            user_key=user_key,
            json_body={"signature": signature},
        )
        return self._sign_result(body)

    def delete_draft(self, didox_id: str, *, user_key: str | None = None) -> DidoxSignResult:
        """Drop an unsent draft (no signature involved)."""
        body = self._request(
            "POST",
            f"/v1/documents/{didox_id}/delete/draft",
            "delete_draft",
            user_key=user_key,
        )
        return self._sign_result(body)

    def list_documents(
        self,
        *,
        page: int = 1,
        limit: int = 50,
        owner: int | None = None,
        status: str | None = None,
        doctype: str | None = None,
        date_from_updated: str | None = None,
        date_to_updated: str | None = None,
        user_key: str | None = None,
    ) -> dict[str, Any]:
        """`GET /v2/documents` — the polling surface. There are no webhooks.

        `page` and `limit` are NOT optional: the endpoint misbehaves without both,
        so they are defaulted rather than left out. `dateFromUpdated` has DAY
        granularity, which is why the poller overlaps its cursor and why every
        consumer downstream must be idempotent.
        """
        params: dict[str, Any] = {"page": page, "limit": min(limit, 100)}
        if owner is not None:
            params["owner"] = owner
        if status is not None:
            params["status"] = status
        if doctype is not None:
            params["doctype"] = doctype
        if date_from_updated is not None:
            params["dateFromUpdated"] = date_from_updated
        if date_to_updated is not None:
            params["dateToUpdated"] = date_to_updated
        body = self._request("GET", "/v2/documents", "list_documents", user_key=user_key, params=params)
        return body if isinstance(body, dict) else {"data": [], "total": 0}

    def archive(self, didox_id: str, *, user_key: str | None = None) -> bytes:
        """The evidence pack: a ZIP (signatures + PDF + JSON) in the body.

        This is the legal artefact. Fetch it once on the transition to signed,
        hash it, store it — do not re-fetch on demand, and do not treat the PDF
        alone as proof.
        """
        body = self._request(
            "GET", f"/v1/documents/{didox_id}/archive", "archive", user_key=user_key, raw=True
        )
        if not isinstance(body, bytes) or not body:
            raise ProviderUnavailable("didox: archive was empty")
        return body

    def print_form(
        self, didox_id: str, *, locale: str = "ru", user_key: str | None = None
    ) -> bytes:
        """The document as the OPERATOR renders it — PDF bytes.

        Not the same artefact as ours. `contracts/render.py` produces what we
        asked the parties to sign; this is what now stands at Didox, carrying
        their electronic-document id and the marks of both signatures — the thing
        that shows up in my.soliq.uz.

        Two routes, differing only in who may ask. `view/…` also checks that the
        document belongs to the acting user, so a cabinet request (which has that
        company's `user-key`) uses it; staff act as nobody and would be refused,
        so without a key we take the partner-token route.

        `raw=True` for the same reason `archive` and `_base64_body` need it: a PDF
        through `resp.json()` raises, and at the call site that is
        indistinguishable from the provider being down.
        """
        path = (
            f"/v1/documents/view/{didox_id}/pdf/{locale}"
            if user_key
            else f"/v1/documents/{didox_id}/pdf/{locale}"
        )
        body = self._request("GET", path, "print_form", user_key=user_key, raw=True)
        if not isinstance(body, bytes) or not body:
            raise ProviderUnavailable("didox: print form was empty")
        return body

    # ── onboarding: signup + the one-time public offer ────────────────────────

    def signup(
        self, signature: str, *, email: str, mobile: str, password: str
    ) -> str:
        """Register a company by ЭЦП → its first `user-key`.

        `signature` is a TIMESTAMPED PKCS#7 over the INN. Note their validator
        REJECTS `+` in an email (verified live), so plus-addressing cannot be used
        to derive per-company addresses.
        """
        body = self._request(
            "POST",
            "/v1/auth/signup",
            "signup",
            json_body={
                "signature": signature,
                "email": email,
                "mobile": mobile,
                "password": password,
            },
        )
        token = (body or {}).get("token") if isinstance(body, dict) else None
        if not token:
            raise ProviderUnavailable("didox: signup response carried no token")
        return str(token)

    def auth_by_eimzo(self, tax_id: str, signature: str, locale: str = "ru") -> str:
        """Mint a `user-key` from a timestamped signature over the INN."""
        body = self._request(
            "POST",
            f"/v1/auth/{tax_id}/token/{locale}",
            "auth_by_eimzo",
            json_body={"signature": signature},
        )
        token = (body or {}).get("token") if isinstance(body, dict) else None
        if not token:
            raise ProviderUnavailable("didox: auth response carried no token")
        return str(token)

    def offer_base64(self, *, user_key: str | None = None) -> str:
        """The current public offer PDF, base64 — to be signed once per company."""
        return self._base64_body("/v1/newoffer/base64", "offer_base64", user_key)

    def create_offer_document(
        self, document_b64: str, *, tax_id: str, user_key: str | None = None
    ) -> dict[str, Any]:
        """Wrap the offer PDF as a document, and return the JSON to be signed.

        The `document_json` in this response — NOT the PDF that went in — is what
        the signature must cover (`reference/11-offer-signing.md` step 3).

        Two quirks of THIS endpoint, both established live and neither documented:

        * **The `Partner-Authorization` value must be the bare token.** It is the
          only endpoint that JWT-verifies the header value itself, so the `Bearer `
          prefix the rest of the API tolerates makes it answer `500
          JsonWebTokenError: invalid token`. `_headers` sends it bare everywhere,
          which satisfies both — do not "fix" that by adding a prefix.
        * **`taxIdOrPinfl` is the acting company's own ИНН**, requested by Didox
          support on 24.08.2026. It does not cure their `Failed to store offer`
          (verified with and without it, in six spellings and two content types),
          but their validator accepts it and it is what they asked for.
        """
        body = self._request(
            "POST",
            "/v1/documents/offer/create",
            "create_offer_document",
            user_key=user_key,
            json_body={"document": document_b64, "taxIdOrPinfl": tax_id},
        )
        envelope = body if isinstance(body, dict) else {}
        document_json = (envelope.get("pending_document") or {}).get("document_json")
        if not isinstance(document_json, dict) or not document_json:
            raise ProviderUnavailable("didox: offer create carried no document_json")
        return document_json

    def sign_offer(self, signature: str, *, user_key: str | None = None) -> DidoxSignResult:
        """Sign the public offer. Until this succeeds the first SEND fails 422."""
        body = self._request(
            "POST",
            "/v1/documents/offer/sign",
            "sign_offer",
            user_key=user_key,
            json_body={"signature": signature},
        )
        return self._sign_result(body)

    # ── profile: ИКПУ + VAT registration ──────────────────────────────────────

    def profile(self, *, user_key: str | None = None) -> dict[str, Any]:
        """The acting company's Didox profile.

        Carries `offerSigned` / `offerDocumentId`, which is the only direct read of
        whether the public offer has been signed. Answers `422 "Failed to get Phis
        By Tin Info info from soliq"` for any company Didox cannot resolve in the
        tax registry — so callers must treat a failure as "unknown", never as
        "not signed".
        """
        body = self._request("GET", "/v1/profile", "profile", user_key=user_key)
        return body if isinstance(body, dict) else {}

    def vat_reg_status(
        self,
        tax_id: str,
        *,
        document_date: str | None = None,
        is_seller: bool | None = None,
        user_key: str | None = None,
    ) -> DidoxVatStatus | None:
        """VAT registration of one party, or `None` when Didox could not tell us.

        **Their failure arrives as HTTP 200 with `{"status": "failed"}`** (verified
        live — the test contour cannot reach soliq). Returning a DTO with empty
        fields for that would put a blank VAT registration code onto a document
        that reaches the tax authority, so it maps to `None` and the caller must
        decide what to do about a missing fact.

        Both parameters change the answer: it is a point-in-time, per-role fact
        and must be read per document, never cached on the company.
        """
        params: dict[str, Any] = {}
        if document_date is not None:
            params["document_date"] = document_date
        if is_seller is not None:
            params["isSeller"] = "true" if is_seller else "false"
        body = self._request(
            "GET",
            f"/v1/profile/vatRegStatus/{tax_id}",
            "vat_reg_status",
            user_key=user_key,
            params=params or None,
        )
        if not isinstance(body, dict) or body.get("status") != "success":
            return None
        return DidoxVatStatus(
            code=_text(body.get("vatRegCode")),
            status=_int(body.get("vatRegStatus")),
            status_code=_text(body.get("vatRegStatusCode")),
        )

    def product_class_codes(
        self,
        *,
        search: str | None = None,
        page: int = 1,
        user_key: str | None = None,
    ) -> list[DidoxProductClass]:
        """ИКПУ rows, each carrying its packages and the ЭСФ `Origin`.

        Whether `search` covers the whole tasnif directory or only the codes bound
        to this company is UNSETTLED — their docs describe the same URL both ways,
        and the live test contour cannot reach its own ИКПУ gateway
        (`Could not resolve host: gnk-gw.didox77.uz`), so it could not be
        confirmed. The leaked upstream path (`company/get/basket-products?…&tin=`)
        suggests per-company. Re-check before relying on it for discovery.
        """
        params: dict[str, Any] = {"page": page}
        if search:
            params["search"] = search
        body = self._request(
            "GET",
            "/v1/profile/productClassCodes",
            "product_class_codes",
            user_key=user_key,
            params=params,
        )
        rows = (body or {}).get("data") if isinstance(body, dict) else None
        return [self._to_product_class(r) for r in rows or [] if isinstance(r, dict)]

    def bind_product_class(self, class_code: str, *, user_key: str | None = None) -> None:
        """Attach an ИКПУ to the acting company's profile."""
        self._request(
            "POST",
            "/v1/profile/productClasses",
            "bind_product_class",
            user_key=user_key,
            json_body={"classCode": class_code},
        )

    def class_packages(
        self, tax_id: str, class_code: str, *, locale: str = "ru", user_key: str | None = None
    ) -> list[tuple[str, str]]:
        """Packages available for one ИКПУ. `locale` is ignored by them — always RU."""
        body = self._request(
            "GET",
            f"/v1/profile/{tax_id}/productClasses/check/{class_code}/{locale}",
            "class_packages",
            user_key=user_key,
        )
        rows = body if isinstance(body, list) else []
        out: list[tuple[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code, name = _text(row.get("code")), _text(row.get("name"))
            if code:
                out.append((code, name or code))
        return out

    # ── plumbing ──────────────────────────────────────────────────────────────

    @staticmethod
    def _sign_result(body: Any) -> DidoxSignResult:  # noqa: ANN401
        """A 200 may carry `warningDetails` — accepted WITH remarks, not failed."""
        envelope = body if isinstance(body, dict) else {}
        warning = envelope.get("warningDetails")
        return DidoxSignResult(
            ok=True,
            warning=warning if isinstance(warning, dict) and warning else None,
        )

    @staticmethod
    def _to_product_class(row: dict[str, Any]) -> DidoxProductClass:
        packages: list[tuple[str, str]] = []
        for pkg in row.get("packages") or []:
            if not isinstance(pkg, dict):
                continue
            code = _text(pkg.get("code"))
            if code:
                packages.append((code, _text(pkg.get("name_ru")) or _text(pkg.get("name")) or code))
        origin = row.get("origin") if isinstance(row.get("origin"), dict) else {}
        return DidoxProductClass(
            class_code=_text(row.get("classCode")) or "",
            name=_text(row.get("className_ru")) or _text(row.get("className")),
            packages=packages,
            origin_id=_int((origin or {}).get("id")),
            origin_name=_text((origin or {}).get("name")),
            use_package=bool(row.get("usePackage")),
        )

    def _headers(self, user_key: str | None) -> dict[str, str]:
        headers = {
            "Partner-Authorization": self._partner_token,
            "Accept-Language": "ru",
        }
        key = user_key or self._user_key
        if key:
            # Only when we actually have one — an empty header reads as a bad key.
            headers["user-key"] = key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        operation: str,
        *,
        user_key: str | None = None,
        json_body: Any = None,  # noqa: ANN401
        params: dict[str, Any] | None = None,
        raw: bool = False,
    ) -> Any:  # noqa: ANN401
        if self._breaker.is_open():
            self._log_call(operation, ok=False, status_code=None, latency_ms=None, error="breaker_open")
            raise ProviderUnavailable("didox: circuit open")

        started = self._clock()
        try:
            with self._client_factory() as client:
                resp = client.request(
                    method,
                    f"{self._base_url}{path}",
                    headers=self._headers(user_key),
                    json=json_body,
                    params=params,
                )
        except httpx.HTTPError as exc:
            self._breaker.record_failure()
            self._log_call(
                operation,
                ok=False,
                status_code=None,
                latency_ms=self._elapsed_ms(started),
                error=type(exc).__name__,
            )
            logger.warning("didox.transport_error", extra={"error": str(exc), "op": operation})
            raise ProviderUnavailable(f"didox: {type(exc).__name__}") from exc

        latency_ms = self._elapsed_ms(started)
        if resp.status_code >= 500:
            self._breaker.record_failure()
            self._log_call(operation, ok=False, status_code=resp.status_code, latency_ms=latency_ms, error="didox_5xx")
            raise ProviderUnavailable(f"didox: {resp.status_code}")

        if resp.status_code in (401, 403):
            # Auth, not content. Prod refuses the lookup without a user-key and
            # says "Token expired"; treating that as a domain answer would let a
            # misconfiguration masquerade as a fact about a company. It is not
            # the provider failing either, so the breaker stays closed.
            self._breaker.record_success()
            self._log_call(operation, ok=False, status_code=resp.status_code, latency_ms=latency_ms, error="didox_auth")
            raise ProviderUnavailable(f"didox: {resp.status_code} {self._message(resp)}")

        if resp.status_code >= 400:
            self._breaker.record_success()
            self._log_call(operation, ok=False, status_code=resp.status_code, latency_ms=latency_ms, error="didox_4xx")
            raise self._to_error(resp)

        self._breaker.record_success()
        self._log_call(operation, ok=True, status_code=resp.status_code, latency_ms=latency_ms, error=None)
        if raw:
            # The evidence archive is a ZIP in the body. Parsing it as JSON would
            # raise on the first real archive we ever fetch.
            return resp.content
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            logger.warning("didox.bad_json", extra={"op": operation})
            return None

    @staticmethod
    def _message(resp: httpx.Response) -> str:
        try:
            payload = resp.json()
        except ValueError:
            return resp.text.strip()[:200] or resp.reason_phrase
        if isinstance(payload, dict):
            message = payload.get("message")
            if isinstance(message, str):
                return message
            # `{"success": false, "error": "..."}` — a third envelope, seen live
            # on the profile/ИКПУ endpoints when THEIR upstream is unreachable.
            # The text names the failing host, which is the only thing that
            # explains the error, so it must not degrade to a reason phrase.
            error = payload.get("error")
            if isinstance(error, str):
                return error
        return resp.reason_phrase

    def _to_error(self, resp: httpx.Response) -> DidoxError:
        """Normalize Didox's several error envelopes into one exception."""
        message = self._message(resp)
        trace_id: str | None = None
        description: str | None = None
        context: Any = None
        try:
            payload = resp.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            details = payload.get("errorDetails")
            if isinstance(details, dict) and details:
                trace_id = _text(details.get("id"))
                description = _text(details.get("description"))
                message = _text(details.get("message")) or message
            data = payload.get("data")
            if isinstance(data, dict) and _text(data.get("message")):
                message = str(data["message"])
            # `context` is where the offer gate identifies itself; it sits at the
            # top level on some shapes and inside `data` on others.
            context = payload.get("context")
            if context is None and isinstance(data, dict):
                context = data.get("context")
        return DidoxError(
            resp.status_code, message, trace_id=trace_id, description=description, context=context
        )

    def _elapsed_ms(self, started: float) -> int:
        return max(0, int((self._clock() - started) * 1000))

    def _log_call(
        self,
        operation: str,
        *,
        ok: bool,
        status_code: int | None,
        latency_ms: int | None,
        error: str | None,
    ) -> None:
        """Best-effort `integration_call_log` row on an isolated session (never raises).

        Metadata only — never a request or response body. A lookup response
        carries a director's ПИНФЛ and a bank account.
        """
        if self._session_factory is None:
            return
        try:
            from app.models.integration import IntegrationCallLog  # noqa: PLC0415

            with self._session_factory() as db:
                db.add(
                    IntegrationCallLog(
                        provider=_PROVIDER,
                        operation=operation,
                        ok=ok,
                        status_code=status_code,
                        latency_ms=latency_ms,
                        error=error,
                    )
                )
                db.commit()
        except Exception as exc:  # noqa: BLE001 — the call log must never break a lookup
            logger.warning("didox.call_log.failed", extra={"error": str(exc)})


# ── Process singleton ──────────────────────────────────────────────────────────

_client: DidoxClient | None = None


def get_didox_client() -> DidoxClient:
    """The process-wide client (call-logs to the app DB via SessionLocal)."""
    global _client
    if _client is None:
        from app.core.db import SessionLocal  # noqa: PLC0415

        _client = DidoxClient(session_factory=SessionLocal)
    return _client


def is_configured() -> bool:
    """True when a partner token exists. Without one every call is a 401, so the
    caller should degrade before spending a request finding that out."""
    from app.core.config import settings  # noqa: PLC0415

    return bool(settings.DIDOX_PARTNER_TOKEN)
