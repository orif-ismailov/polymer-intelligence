"""Standalone Didox partner-API client (httpx only).

Covers the published surface of https://api-docs.didox.uz/ru/ — auth, DSVS
(timestamp / signature join), the document lifecycle, the one-time offer
signature, catalogs and the utils most integrations need.

Two uses:

1. **Runnable** — smoke a test-contour credential without touching an app:

       python didox_client.py login --tin 123456789 --password ***
       python didox_client.py docs --user-key <uuid> --owner 1 --status 3
       python didox_client.py get --user-key <uuid> --id 11f092e3428d10c68f7b

2. **A port target** — this is the shape to move into
   `backend/app/integrations/didox/client.py`, wrapped in the repo's gateway
   pattern (`integrations/eimzo/client.py`): CircuitBreaker, ProviderUnavailable,
   an `integration_call_log` row per call on an isolated session, and the
   4xx = domain result / 5xx = outage split. Deliberately left out here so the
   file stays runnable outside the app.

What this file does NOT do: create signatures. The private key lives on the
user's machine behind the local E-IMZO module (CAPIWS, `wss://127.0.0.1:64443`),
so PKCS#7 creation happens in the browser. See `sign_flow.py` for the
orchestration and `../reference/01-eimzo.md` for the protocol.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from dataclasses import dataclass
from typing import Any, Literal

import httpx

TEST_BASE_URL = "https://testapi3.didox.uz"
PROD_BASE_URL = "https://api-partners.didox.uz"

Locale = Literal["ru", "uz"]

# ── Document types (POST /v1/documents/{docType}/create/{locale}) ──────────────
DOC_TYPES: dict[str, str] = {
    "002": "Счёт-фактура (ЭСФ) без акта",
    "008": "Счёт-фактура (ФАРМ)",
    "023": "Гибридная счёт-фактура",
    "041": "ТТН (товарно-транспортная накладная)",
    "005": "Акт выполненных работ",
    "006": "Доверенность",
    "062": "Доверенность (новая)",
    "007": "Договор (ГНК) — «Договор НК»",
    "000": "Произвольный документ (PDF ≤ 10 МБ, не уходит в роуминг)",
    "010": "Многосторонний произвольный документ",
    "052": "Акт сверки",
    "054": "Акт приёма-передачи",
    "075": "Протокол собрания учредителей",
    "031": "Письмо НК",
}

# ── Statuses. NOTE: ТТН and доверенность(новая) run their own ladders. ─────────
STATUSES: dict[int, str] = {
    0: "Черновик",
    1: "Ожидает подписи партнёра",
    2: "Ожидает вашей подписи",
    3: "Подписан",
    4: "Отказ от подписи",
    5: "Удалён",
    6: "Ожидает подписи агента",
    8: "Подписан агентом",
    40: "Недействительный",
    50: "Аннулирован НК",
    55: "Черновик удалён",
    60: "Ожидает подписи агента (у получателя)",
}
TTN_STATUSES: dict[int, str] = {
    110: "Отправлено",
    140: "Принято отв. лицом",
    150: "Груз возвращён",
    160: "Доставлено получателю",
    170: "Отказано грузополучателем",
    190: "Груз возвращён отв. лицом",
    200: "Подтверждение отправителя о возврате товара",
}

SIGNED = 3
AWAITING_PARTNER = 1
AWAITING_YOU = 2

ToSignAction = Literal[
    "accept",
    "cancel",
    "reject",
    "responsibleGive",
    "responsibleAccept",
    "responsibleTillReturn",
    "responsibleReturn",
    "consignorReturn",
    "consignorReturnAccept",
    "accountantAccept",
    "agentAccept",
]


class DidoxError(Exception):
    """A Didox API call failed.

    `trace_id` is the `x-trace-id` echoed in `errorDetails.id` — quote it to
    support. `description` is Didox's own "what to do about it" text, present
    only for errors it has an explanation for, in `Accept-Language`.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        trace_id: str | None = None,
        description: str | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(f"didox {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.trace_id = trace_id
        self.description = description
        self.payload = payload

    @property
    def offer_not_signed(self) -> bool:
        """True for the 422 that means the user has never signed the public offer.

        The single most common first-integration failure — fix it by running the
        offer flow (`sign_flow.sign_offer`), not by retrying.
        """
        return "оферта не подписана" in self.message.lower() or (
            isinstance(self.payload, dict)
            and isinstance(self.payload.get("data"), dict)
            and (self.payload["data"].get("context") or {}).get("offer") == "required"
        )


@dataclass(frozen=True)
class AuthResult:
    """A minted user-key plus whatever context the auth method returned."""

    token: str
    tax_id: str | None = None
    name: str | None = None
    permissions: dict[str, Any] | None = None
    related_companies: Any = None
    related_branches: Any = None


@dataclass(frozen=True)
class SignResult:
    """Outcome of a /sign call.

    `warnings` is `warningDetails` — a 200 that carries remarks from the tax
    committee. It is NOT a failure; log it and carry on.
    """

    ok: bool
    warnings: dict[str, Any] | None = None


def b64(value: str | bytes) -> str:
    """UTF-8 → base64, the encoding every `create_pkcs7` argument wants."""
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return base64.b64encode(raw).decode("ascii")


def json_b64(document_json: Any) -> str:
    """Serialize a document JSON exactly as it must be signed.

    Compact separators, no ASCII escaping — the bytes you sign have to be the
    bytes Didox stored, so never re-format the `json` you read back from
    `GET /v1/documents/{id}`.
    """
    if isinstance(document_json, str):
        return b64(document_json)
    return b64(json.dumps(document_json, ensure_ascii=False, separators=(",", ":")))


class DidoxClient:
    """Thin, typed wrapper over the Didox partner API.

    `partner_token` is a server-side secret and goes on EVERY request, including
    auth. `user_key` identifies the acting user/company and expires after 360
    minutes — pass it per call or set it once on the instance.
    """

    def __init__(
        self,
        *,
        partner_token: str,
        base_url: str = TEST_BASE_URL,
        user_key: str | None = None,
        locale: Locale = "ru",
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.partner_token = partner_token
        self.user_key = user_key
        self.locale: Locale = locale
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=timeout, write=timeout, pool=5.0)
        )

    # ── plumbing ──────────────────────────────────────────────────────────────

    def _headers(self, user_key: str | None, *, json_body: bool = True) -> dict[str, str]:
        headers = {
            "Partner-Authorization": self.partner_token,
            "Accept-Language": self.locale,
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        key = user_key or self.user_key
        if key:
            headers["user-key"] = key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        user_key: str | None = None,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        raw: bool = False,
    ) -> Any:
        resp = self._client.request(
            method,
            f"{self.base_url}/{path.lstrip('/')}",
            headers=self._headers(user_key, json_body=json_body is not None),
            json=json_body,
            params={k: v for k, v in (params or {}).items() if v is not None},
        )
        if resp.status_code >= 400:
            raise self._to_error(resp)
        if raw:
            return resp.content
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.content

    @staticmethod
    def _to_error(resp: httpx.Response) -> DidoxError:
        """Normalize Didox's several error envelopes into one exception."""
        message: str = resp.text.strip() or resp.reason_phrase
        trace_id: str | None = None
        description: str | None = None
        payload: Any = None
        try:
            payload = resp.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            details = payload.get("errorDetails") or {}
            if isinstance(details, dict) and details:
                trace_id = details.get("id")
                description = details.get("description")
                message = details.get("message") or message
            data = payload.get("data")
            if isinstance(data, dict) and data.get("message"):
                message = str(data["message"])
            elif isinstance(payload.get("message"), str):
                message = payload["message"]
            elif isinstance(payload.get("error"), dict):
                message = str(payload["error"].get("message") or message)
            else:
                # field-validation shape: {"signature": ["required"]}
                fields = {
                    k: v for k, v in payload.items()
                    if isinstance(v, list) and k not in {"data", "errorDetails"}
                }
                if fields:
                    message = "; ".join(f"{k}: {', '.join(map(str, v))}" for k, v in fields.items())
        return DidoxError(
            resp.status_code, message, trace_id=trace_id, description=description, payload=payload
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DidoxClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── auth (reference/02-registration.md, 03-login.md) ───────────────────────

    def signup(self, signature: str, **fields: Any) -> AuthResult:
        """POST /v1/auth/signup — register a user by ЭЦП.

        `signature` is `timeStampTokenB64` (a timestamped PKCS#7 of the INN),
        not the bare pkcs7_64.
        """
        body = {"signature": signature, **fields}
        return self._to_auth(self._request("POST", "/v1/auth/signup", json_body=body))

    def auth_by_eimzo(self, tax_id: str, signature: str, locale: Locale | None = None) -> AuthResult:
        """POST /v1/auth/{taxId}/token/{locale} — mint a user-key from a signature over the INN."""
        path = f"/v1/auth/{tax_id}/token/{locale or self.locale}"
        return self._to_auth(self._request("POST", path, json_body={"signature": signature}))

    def auth_by_password(
        self, tax_id: str, password: str, locale: Locale | None = None
    ) -> AuthResult:
        """POST /v1/auth/{taxId}/password/{locale}.

        Lockout ladder: 3 failures/min → 10 min, 10 → 24 h, 25 → permanent.
        Never retry this in a loop.
        """
        path = f"/v1/auth/{tax_id}/password/{locale or self.locale}"
        return self._to_auth(self._request("POST", path, json_body={"password": password}))

    def login_company(
        self,
        company_tax_id: str,
        *,
        user_key: str,
        branch_num: str | None = None,
        locale: Locale | None = None,
    ) -> AuthResult:
        """POST /v1/auth/company/{companyTaxId}/login/{locale} — individual token → company token.

        `user_key` here is the INDIVIDUAL's token from auth_by_eimzo/password;
        the returned token carries `permissions.roles[]` inside that company.
        """
        path = f"/v1/auth/company/{company_tax_id}/login/{locale or self.locale}"
        body = {"branchNum": branch_num} if branch_num else None
        return self._to_auth(self._request("POST", path, user_key=user_key, json_body=body))

    @staticmethod
    def _to_auth(payload: Any) -> AuthResult:
        if not isinstance(payload, dict) or not payload.get("token"):
            raise DidoxError(200, "auth response carried no token", payload=payload)
        return AuthResult(
            token=str(payload["token"]),
            tax_id=payload.get("taxId"),
            name=payload.get("name"),
            permissions=payload.get("permissions"),
            related_companies=payload.get("related_companies"),
            related_branches=payload.get("related_branches"),
        )

    # ── DSVS: timestamp + join (reference/01-eimzo.md §4) ──────────────────────

    def timestamp(self, pkcs7_64: str, signature_hex: str) -> str:
        """POST /v1/dsvs/timestamp → timeStampTokenB64.

        MANDATORY after every `create_pkcs7`. A bare pkcs7_64 is rejected by every
        endpoint that takes a `signature`.
        """
        payload = self._request(
            "POST", "/v1/dsvs/timestamp",
            json_body={"pkcs7": pkcs7_64, "signatureHex": signature_hex},
        )
        token = (payload or {}).get("timeStampTokenB64")
        if not token:
            raise DidoxError(200, "timestamp response carried no token", payload=payload)
        return str(token)

    def join_signatures(self, signature1: str, signature2: str) -> str:
        """POST /v1/dsvs/signature/join → pkcs7B64.

        Incoming documents only: `signature1` is the sender's `toSign`,
        `signature2` is yours. Order matters.
        """
        payload = self._request(
            "POST", "/v1/dsvs/signature/join",
            json_body={"signature1": signature1, "signature2": signature2},
        )
        joined = (payload or {}).get("pkcs7B64")
        if not joined:
            raise DidoxError(200, "join response carried no pkcs7B64", payload=payload)
        return str(joined)

    # ── documents (reference/06-documents.md) ──────────────────────────────────

    def list_documents(
        self,
        *,
        page: int = 1,
        limit: int = 20,
        owner: int | None = None,
        status: str | int | None = None,
        doctype: str | None = None,
        partner: str | None = None,
        date_from_updated: str | None = None,
        date_to_updated: str | None = None,
        user_key: str | None = None,
        **extra: Any,
    ) -> Any:
        """GET /v2/documents. `page` and `limit` are MANDATORY (limit ≤ 100).

        `owner`: 1 outgoing, 0 incoming (absent = outgoing). `status`/`doctype`
        accept comma-separated multi-values. `date_*_updated` (yyyy-mm-dd) is the
        incremental-poll cursor — Didox has no partner webhooks.
        """
        params = {
            "page": page, "limit": min(limit, 100), "owner": owner, "status": status,
            "doctype": doctype, "partner": partner,
            "dateFromUpdated": date_from_updated, "dateToUpdated": date_to_updated,
            **extra,
        }
        return self._request("GET", "/v2/documents", params=params, user_key=user_key)

    def statistics(self, user_key: str | None = None) -> Any:
        """GET /v2/documents/statistics/all — per-status counters."""
        return self._request("GET", "/v2/documents/statistics/all", user_key=user_key)

    def get_document(self, doc_id: str, *, owner: int | None = None, user_key: str | None = None) -> Any:
        """GET /v1/documents/{id}. Pass owner=1 for outgoing (gives `json`),
        owner=0 for incoming (gives `toSign`)."""
        return self._request(
            "GET", f"/v1/documents/{doc_id}", params={"owner": owner}, user_key=user_key
        )

    def create_document(
        self, doc_type: str, document: Any, *, locale: Locale | None = None, user_key: str | None = None
    ) -> Any:
        """POST /v1/documents/{docType}/create/{locale} → draft.

        `document` is the PascalCase payload from reference/07-document-json.md.
        The response echoes it back as `document_json` with every key LOWERCASED —
        your writer and reader are not symmetric.
        """
        path = f"/v1/documents/{doc_type}/create/{locale or self.locale}"
        return self._request("POST", path, json_body=document, user_key=user_key)

    def update_draft(
        self,
        doc_id: str,
        doc_type: str,
        document: Any,
        *,
        locale: Locale | None = None,
        user_key: str | None = None,
    ) -> Any:
        """POST /v1/documents/{id}/update/{docType}/{locale}."""
        path = f"/v1/documents/{doc_id}/update/{doc_type}/{locale or self.locale}"
        return self._request("POST", path, json_body=document, user_key=user_key)

    def delete_draft(self, doc_id: str, *, user_key: str | None = None) -> Any:
        """POST /v1/documents/{id}/delete/draft — drafts only."""
        return self._request("POST", f"/v1/documents/{doc_id}/delete/draft", user_key=user_key)

    def to_sign(
        self,
        doc_id: str,
        action: ToSignAction,
        *,
        comment: str | None = None,
        user_key: str | None = None,
    ) -> Any:
        """POST /v1/documents/{id}/tosign → what to sign for `action`.

        Returns the raw `data` field, which is EITHER an object to sign, OR an
        already-built base64 signature string, OR empty — depending on the
        (action, docType) pair. Branch on the runtime type; see sign_flow.py.
        """
        body: dict[str, Any] = {"action": action}
        if comment is not None:
            body["comment"] = comment
        payload = self._request(
            "POST", f"/v1/documents/{doc_id}/tosign", json_body=body, user_key=user_key
        )
        return (payload or {}).get("data")

    def document_base64(self, doc_id: str, *, user_key: str | None = None) -> Any:
        """GET /v1/documents/{id}/documentBase64 — the bytes to sign for an INCOMING doc."""
        return self._request("GET", f"/v1/documents/{doc_id}/documentBase64", user_key=user_key)

    def sign(self, doc_id: str, signature: str, *, user_key: str | None = None) -> SignResult:
        """POST /v1/documents/{id}/sign — signing IS sending.

        Raises DidoxError on 422 «Оферта не подписана» (check `.offer_not_signed`),
        403 (no permission), 503 (tax-committee timeout — check status before retry).
        """
        payload = self._request(
            "POST", f"/v1/documents/{doc_id}/sign",
            json_body={"signature": signature}, user_key=user_key,
        )
        payload = payload or {}
        return SignResult(ok=bool(payload.get("data")), warnings=payload.get("warningDetails"))

    def reject(
        self, doc_id: str, signature: str, comment: str, *, user_key: str | None = None
    ) -> Any:
        """POST /v1/documents/{id}/reject.

        `comment` must be byte-identical to the one passed to `to_sign(action="reject")`.
        """
        return self._request(
            "POST", f"/v1/documents/{doc_id}/reject",
            json_body={"signature": signature, "comment": comment}, user_key=user_key,
        )

    def cancel(self, doc_id: str, signature: str, *, user_key: str | None = None) -> Any:
        """POST /v1/documents/{id}/delete — cancel an already-sent outgoing document."""
        return self._request(
            "POST", f"/v1/documents/{doc_id}/delete",
            json_body={"signature": signature}, user_key=user_key,
        )

    # ТТН responsible-person actions — each preceded by the matching to_sign action.
    def ttn_give(self, doc_id: str, signature: str, *, user_key: str | None = None) -> Any:
        """POST /v1/documents/{id}/give — requires status 140/240 (принято отв. лицом)."""
        return self._request(
            "POST", f"/v1/documents/{doc_id}/give",
            json_body={"signature": signature}, user_key=user_key,
        )

    def ttn_till_return(self, doc_id: str, signature: str, *, user_key: str | None = None) -> Any:
        """POST /v1/documents/{id}/tillreturn — return at the accepted stage."""
        return self._request(
            "POST", f"/v1/documents/{doc_id}/tillreturn",
            json_body={"signature": signature}, user_key=user_key,
        )

    def ttn_return(self, doc_id: str, signature: str, *, user_key: str | None = None) -> Any:
        """POST /v1/documents/{id}/return — return delivered goods."""
        return self._request(
            "POST", f"/v1/documents/{doc_id}/return",
            json_body={"signature": signature}, user_key=user_key,
        )

    def print_form(
        self,
        doc_id: str,
        fmt: Literal["html", "pdf"] = "pdf",
        *,
        locale: Locale | None = None,
        user_key: str | None = None,
    ) -> bytes:
        """GET /v1/documents/view/{id}/{html|pdf}/{locale} — presentation only, not evidence."""
        path = f"/v1/documents/view/{doc_id}/{fmt}/{locale or self.locale}"
        return self._request("GET", path, user_key=user_key, raw=True)

    def archive(self, doc_id: str, *, user_key: str | None = None) -> bytes:
        """GET /v1/documents/{id}/archive → ZIP bytes (signatures + PDF + JSON).

        THE legal evidence pack. Fetch once on transition to signed, hash it,
        store it — don't re-fetch on demand and don't treat the PDF as proof.
        """
        return self._request("GET", f"/v1/documents/{doc_id}/archive", user_key=user_key, raw=True)

    def contract_info(
        self, contract_id: str, *, locale: Locale | None = None, user_key: str | None = None
    ) -> Any:
        """GET /v1/documents/contract/{contractId}/info/{locale} — prefill an ЭСФ from a договор."""
        path = f"/v1/documents/contract/{contract_id}/info/{locale or self.locale}"
        return self._request("GET", path, user_key=user_key)

    # ── one-time public offer (reference/11-offer-signing.md) ──────────────────

    def offer_base64(self, *, user_key: str | None = None) -> Any:
        """GET /v1/newoffer/base64 — the offer text to sign."""
        return self._request("GET", "/v1/newoffer/base64", user_key=user_key)

    def create_offer_document(self, body: Any = None, *, user_key: str | None = None) -> Any:
        """POST /v1/documents/offer/create."""
        return self._request("POST", "/v1/documents/offer/create", json_body=body or {}, user_key=user_key)

    def sign_offer(self, signature: str, *, user_key: str | None = None) -> Any:
        """POST /v1/documents/offer/sign — unblocks every later /sign call."""
        return self._request(
            "POST", "/v1/documents/offer/sign",
            json_body={"signature": signature}, user_key=user_key,
        )

    # ── catalogs & utils (reference/09-catalogs.md, 08-utils.md) ───────────────

    def banks(self, *, user_key: str | None = None) -> Any:
        """GET /v1/banks/all — МФО classifier."""
        return self._request("GET", "/v1/banks/all", user_key=user_key)

    def measures(self, *, user_key: str | None = None) -> Any:
        """GET /v1/measures/all — units of measure (packagecode/packagename)."""
        return self._request("GET", "/v1/measures/all", user_key=user_key)

    def regions(self, *, user_key: str | None = None) -> Any:
        """GET /v1/regions/all."""
        return self._request("GET", "/v1/regions/all", user_key=user_key)

    def districts(self, *, user_key: str | None = None) -> Any:
        """GET /v1/districts/all."""
        return self._request("GET", "/v1/districts/all", user_key=user_key)

    def info_by_tin(self, tin_or_pinfl: str, *, user_key: str | None = None) -> Any:
        """GET /v1/utils/info/{TinOrPinfl} — counterparty lookup by INN/ПИНФЛ."""
        return self._request("GET", f"/v1/utils/info/{tin_or_pinfl}", user_key=user_key)


# ── CLI ────────────────────────────────────────────────────────────────────────

def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Didox partner-API smoke client. Needs a partner token from the "
                    "account manager (t.me/Didox_account).",
    )
    parser.add_argument("--base-url", default=TEST_BASE_URL, help=f"default: {TEST_BASE_URL}")
    parser.add_argument("--partner-token", required=True, help="Partner-Authorization header")
    parser.add_argument("--user-key", help="an existing user token (UUID, TTL 360 min)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_login = sub.add_parser("login", help="mint a user-key by password")
    p_login.add_argument("--tin", required=True)
    p_login.add_argument("--password", required=True)

    p_company = sub.add_parser("company", help="enter a company with an individual's token")
    p_company.add_argument("--company-tin", required=True)

    p_docs = sub.add_parser("docs", help="list documents")
    p_docs.add_argument("--page", type=int, default=1)
    p_docs.add_argument("--limit", type=int, default=20)
    p_docs.add_argument("--owner", type=int, choices=[0, 1])
    p_docs.add_argument("--status")
    p_docs.add_argument("--doctype")
    p_docs.add_argument("--since", help="dateFromUpdated, yyyy-mm-dd")

    p_get = sub.add_parser("get", help="document detail")
    p_get.add_argument("--id", required=True)
    p_get.add_argument("--owner", type=int, choices=[0, 1], default=1)

    p_arch = sub.add_parser("archive", help="download the evidence ZIP")
    p_arch.add_argument("--id", required=True)
    p_arch.add_argument("--out", default="document.zip")

    sub.add_parser("doctypes", help="print the document-type table")

    args = parser.parse_args(argv)

    if args.cmd == "doctypes":
        for code, label in DOC_TYPES.items():
            print(f"{code}  {label}")
        return 0

    with DidoxClient(
        partner_token=args.partner_token, base_url=args.base_url, user_key=args.user_key
    ) as client:
        try:
            if args.cmd == "login":
                out: Any = client.auth_by_password(args.tin, args.password)
                print(f"user-key: {out.token}")
                if out.related_companies:
                    print(json.dumps(out.related_companies, ensure_ascii=False, indent=2))
                return 0
            if args.cmd == "company":
                if not args.user_key:
                    parser.error("--user-key (the individual's token) is required")
                out = client.login_company(args.company_tin, user_key=args.user_key)
                print(f"company token: {out.token}\npermissions: {out.permissions}")
                return 0
            if args.cmd == "docs":
                out = client.list_documents(
                    page=args.page, limit=args.limit, owner=args.owner,
                    status=args.status, doctype=args.doctype, date_from_updated=args.since,
                )
            elif args.cmd == "get":
                out = client.get_document(args.id, owner=args.owner)
            elif args.cmd == "archive":
                data = client.archive(args.id)
                with open(args.out, "wb") as fh:
                    fh.write(data)
                print(f"wrote {len(data)} bytes → {args.out}")
                return 0
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0
        except DidoxError as exc:
            print(f"ERROR {exc.status_code}: {exc.message}", file=sys.stderr)
            if exc.description:
                print(f"  → {exc.description}", file=sys.stderr)
            if exc.trace_id:
                print(f"  x-trace-id: {exc.trace_id}", file=sys.stderr)
            if exc.offer_not_signed:
                print("  → the public offer is unsigned: run the offer flow first "
                      "(reference/11-offer-signing.md)", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(_main())
