"""The Didox signing flows, as orchestration you can actually test.

Every Didox signature is the same four steps (list key → load key → create_pkcs7
→ timestamp), but *what* gets signed and *how the result is assembled* differs
per flow, and that ordering is where integrations break. This module encodes the
ordering once, over an injectable `Signer`, so the flows can be unit-tested
without a smart card and reused verbatim behind a browser bridge.

Split of responsibilities in a real deployment:

    browser (portal/src/shared/lib/eimzo/capiws.ts)   backend (this + didox_client)
    ─────────────────────────────────────────────    ──────────────────────────────
    list_all_certificates / load_key / create_pkcs7   POST /v1/dsvs/timestamp
    → pkcs7_64, signature_hex  ──── our API ───────▶  POST /v1/documents/{id}/sign

The private key never leaves the user's machine and the partner token never
reaches the browser. `Signer` is the seam between those two columns.

Run the self-check (no network, no key):

    python sign_flow.py --selfcheck
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from didox_client import DidoxClient, DidoxError, SignResult, b64, json_b64


@dataclass(frozen=True)
class RawSignature:
    """What CAPIWS `create_pkcs7` hands back, before timestamping."""

    pkcs7_64: str
    signature_hex: str


class Signer(Protocol):
    """Creates a PKCS#7 over base64 data using a key we never see.

    In production this is an RPC to the browser (or the queued round-trip that
    waits for the user to click "sign"); in tests it is a fake.
    """

    def sign(self, data_b64: str) -> RawSignature: ...


def _timestamped(client: DidoxClient, signer: Signer, data_b64: str) -> str:
    """create_pkcs7 → /v1/dsvs/timestamp → timeStampTokenB64.

    Never skip the timestamp: a bare pkcs7_64 is rejected by every endpoint that
    takes a `signature`.
    """
    raw = signer.sign(data_b64)
    return client.timestamp(raw.pkcs7_64, raw.signature_hex)


# ── 1. Authentication ─────────────────────────────────────────────────────────

def authenticate(client: DidoxClient, tax_id: str, signer: Signer) -> str:
    """Mint a user-key by ЭЦП. The signed payload is the INN itself, base64'd.

    Returns a UUID valid for 360 minutes. It cannot be minted server-side — the
    signature requires the user's key — so cache it (Redis, TTL well under 360
    min) and re-prompt on expiry rather than failing the action silently.
    """
    signature = _timestamped(client, signer, b64(tax_id))
    return client.auth_by_eimzo(tax_id, signature).token


# ── 2. The one-time public offer ──────────────────────────────────────────────

def sign_public_offer(client: DidoxClient, signer: Signer, *, user_key: str | None = None) -> Any:
    """Sign the Didox public offer. Do this ONCE per user/company, at onboarding.

    Until it is done, every `/sign` returns 422 with `context.offer == "required"`
    — which reads like a document problem and is not one.
    """
    offer = client.offer_base64(user_key=user_key)
    payload = offer.get("data") if isinstance(offer, dict) else offer
    offer_b64 = payload if isinstance(payload, str) else json_b64(payload)

    client.create_offer_document(user_key=user_key)
    signature = _timestamped(client, signer, offer_b64)
    return client.sign_offer(signature, user_key=user_key)


def ensure_offer_signed(client: DidoxClient, signer: Signer, *, user_key: str | None = None) -> bool:
    """Retry-once wrapper: sign the offer if that is why a call failed.

    Use it around a first send. Returns True if it actually signed the offer.
    """
    try:
        client.list_documents(page=1, limit=1, user_key=user_key)
        return False
    except DidoxError as exc:
        if not exc.offer_not_signed:
            raise
        sign_public_offer(client, signer, user_key=user_key)
        return True


# ── 3. Outgoing documents ─────────────────────────────────────────────────────

def create_and_sign(
    client: DidoxClient,
    doc_type: str,
    document: Any,
    signer: Signer,
    *,
    user_key: str | None = None,
) -> tuple[str, SignResult]:
    """Draft → sign → sent, in one call. Signing IS sending; there is no /send.

    Returns (document_id, SignResult). A non-null `SignResult.warnings` is a
    remark from the tax committee on a SUCCESSFUL send — log it, don't fail.
    """
    created = client.create_document(doc_type, document, user_key=user_key)
    doc_id = extract_document_id(created)
    return doc_id, sign_outgoing(client, doc_id, signer, user_key=user_key)


def sign_outgoing(
    client: DidoxClient, doc_id: str, signer: Signer, *, user_key: str | None = None
) -> SignResult:
    """Sign a document we are sending.

    Sign the STORED json — read it back with `?owner=1` rather than re-serializing
    what you posted. Didox lowercases every key on store, so the bytes you sent
    and the bytes it holds are different bytes, and only the latter verify.
    """
    detail = client.get_document(doc_id, owner=1, user_key=user_key)
    document_json = extract_json(detail)
    signature = _timestamped(client, signer, json_b64(document_json))
    return client.sign(doc_id, signature, user_key=user_key)


# ── 4. Incoming documents ─────────────────────────────────────────────────────

def sign_incoming(
    client: DidoxClient, doc_id: str, signer: Signer, *, user_key: str | None = None
) -> SignResult:
    """Accept an incoming document by joining our signature to the sender's.

    Requires E-IMZO >= 6.3.5 on the client machine. The join order is fixed:
    signature1 = the sender's `toSign`, signature2 = ours.
    """
    raw_b64 = client.document_base64(doc_id, user_key=user_key)
    content = raw_b64.get("data") if isinstance(raw_b64, dict) else raw_b64
    ours = _timestamped(client, signer, content if isinstance(content, str) else json_b64(content))

    detail = client.get_document(doc_id, owner=0, user_key=user_key)
    theirs = extract_field(detail, "toSign", "tosign")
    if not theirs:
        raise DidoxError(200, f"document {doc_id} carried no toSign", payload=detail)

    joined = client.join_signatures(theirs, ours)
    return client.sign(doc_id, joined, user_key=user_key)


# ── 5. Actions: reject / cancel / ТТН ─────────────────────────────────────────

def perform_action(
    client: DidoxClient,
    doc_id: str,
    action: Any,
    signer: Signer,
    *,
    comment: str | None = None,
    user_key: str | None = None,
) -> str:
    """`tosign` → sign → return the timestamped signature for the action endpoint.

    `tosign` returns THREE possible shapes and each needs different handling:
      * a dict   → sign its compact JSON;
      * a string → an already-built signature; pass it through untouched;
      * empty    → the (action, docType) pair needs no signature.
    Getting this wrong produces a signature over the literal text "None".
    """
    data = client.to_sign(doc_id, action, comment=comment, user_key=user_key)
    if data in (None, "", {}, []):
        return ""
    if isinstance(data, str):
        return data
    return _timestamped(client, signer, json_b64(data))


def reject_document(
    client: DidoxClient, doc_id: str, comment: str, signer: Signer, *, user_key: str | None = None
) -> Any:
    """Refuse an incoming document. The comment must be IDENTICAL in both calls."""
    signature = perform_action(
        client, doc_id, "reject", signer, comment=comment, user_key=user_key
    )
    return client.reject(doc_id, signature, comment, user_key=user_key)


def cancel_document(
    client: DidoxClient, doc_id: str, signer: Signer, *, user_key: str | None = None
) -> Any:
    """Cancel an already-sent outgoing document."""
    signature = perform_action(client, doc_id, "cancel", signer, user_key=user_key)
    return client.cancel(doc_id, signature, user_key=user_key)


# ── 6. Polling (there are no partner webhooks) ────────────────────────────────

def poll_updated(
    client: DidoxClient,
    since: str,
    *,
    owner: int | None = None,
    doctype: str | None = None,
    user_key: str | None = None,
    page_limit: int = 100,
) -> list[dict[str, Any]]:
    """Walk every document updated on/after `since` (yyyy-mm-dd).

    Didox publishes no partner webhooks, so this is the delivery mechanism.
    `dateFromUpdated` has DAY granularity — overlap the window by a day and make
    the consumer idempotent; do not use it as an exactly-once cursor.
    """
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = client.list_documents(
            page=page, limit=page_limit, owner=owner, doctype=doctype,
            date_from_updated=since, user_key=user_key,
        )
        rows = extract_rows(payload)
        out.extend(rows)
        if len(rows) < page_limit:
            return out
        page += 1


# ── payload helpers — Didox's envelopes are not uniform ───────────────────────

def extract_field(payload: Any, *names: str) -> Any:
    """Find the first of `names` at the top level or one level down.

    Responses nest under `data`, `pending_document` or nothing at all depending
    on the endpoint, and keys are sometimes lowercased. This absorbs that.
    """
    if not isinstance(payload, dict):
        return None
    lowered = {str(k).lower(): v for k, v in payload.items()}
    for name in names:
        if name in payload:
            return payload[name]
        if name.lower() in lowered:
            return lowered[name.lower()]
    for container in ("data", "pending_document", "document"):
        nested = payload.get(container)
        if isinstance(nested, dict):
            found = extract_field(nested, *names)
            if found is not None:
                return found
    return None


def extract_document_id(payload: Any) -> str:
    """Pull the document id out of a create/detail response."""
    found = extract_field(payload, "id", "documentId", "document_id", "doc_id", "didoxorderid")
    if not found:
        raise DidoxError(200, "response carried no document id", payload=payload)
    return str(found)


def extract_json(payload: Any) -> Any:
    """Pull the signable document JSON out of a detail response."""
    found = extract_field(payload, "json", "document_json", "documentJson")
    if found is None:
        raise DidoxError(200, "response carried no document json", payload=payload)
    return found


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    """Pull the row list out of a paginated /v2/documents response."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "documents", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
            if isinstance(value, dict):
                nested = extract_rows(value)
                if nested:
                    return nested
    return []


# ── self-check: exercises the ordering with a fake signer and a fake API ──────

def _selfcheck() -> int:
    calls: list[tuple[str, str]] = []

    class FakeSigner:
        def sign(self, data_b64: str) -> RawSignature:
            calls.append(("sign", data_b64))
            return RawSignature(pkcs7_64=f"PKCS7({data_b64})", signature_hex="deadbeef")

    class FakeClient(DidoxClient):
        def __init__(self) -> None:  # noqa: D107 — no network
            self.locale = "ru"

        def timestamp(self, pkcs7_64: str, signature_hex: str) -> str:
            calls.append(("timestamp", pkcs7_64))
            return f"TS({pkcs7_64})"

        def join_signatures(self, signature1: str, signature2: str) -> str:
            calls.append(("join", f"{signature1}|{signature2}"))
            return f"JOINED({signature1},{signature2})"

        def get_document(self, doc_id, *, owner=None, user_key=None):  # type: ignore[no-untyped-def]
            if owner == 1:
                return {"data": {"json": {"contractdoc": {"contractno": "42"}}}}
            return {"data": {"toSign": "THEIRS"}}

        def document_base64(self, doc_id, *, user_key=None):  # type: ignore[no-untyped-def]
            return {"data": "RE9DVU1FTlQ="}

        def sign(self, doc_id, signature, *, user_key=None):  # type: ignore[no-untyped-def]
            calls.append(("POST /sign", signature))
            return SignResult(ok=True)

        def to_sign(self, doc_id, action, *, comment=None, user_key=None):  # type: ignore[no-untyped-def]
            return {"DocumentId": doc_id, "SellerTin": "302936161"} if action == "cancel" else "READY_B64"

    client = FakeClient()
    signer = FakeSigner()
    failures: list[str] = []

    def check(label: str, got: Any, want: Any) -> None:
        if got != want:
            failures.append(f"{label}\n  got:  {got!r}\n  want: {want!r}")

    # outgoing: sign the STORED json, compact, then timestamp, then POST
    calls.clear()
    sign_outgoing(client, "doc1", signer)
    signed_bytes = json_b64({"contractdoc": {"contractno": "42"}})
    check("outgoing signs the stored json", calls[0], ("sign", signed_bytes))
    check("outgoing timestamps before POST", calls[1][0], "timestamp")
    check("outgoing posts the timestamped token", calls[2], ("POST /sign", f"TS(PKCS7({signed_bytes}))"))

    # incoming: ours is signature2, theirs is signature1
    calls.clear()
    sign_incoming(client, "doc2", signer)
    check("incoming signs documentBase64", calls[0], ("sign", "RE9DVU1FTlQ="))
    check("incoming joins theirs-then-ours", calls[2], ("join", "THEIRS|TS(PKCS7(RE9DVU1FTlQ=))"))
    check("incoming posts the joined pkcs7", calls[3][0], "POST /sign")

    # action returning an object → sign it; returning a string → pass through
    calls.clear()
    got = perform_action(client, "doc3", "cancel", signer)
    want_data = json_b64({"DocumentId": "doc3", "SellerTin": "302936161"})
    check("object action is signed", got, f"TS(PKCS7({want_data}))")
    check("passthrough action is not re-signed", perform_action(client, "doc3", "accept", signer), "READY_B64")

    # auth signs the bare INN
    calls.clear()
    _timestamped(client, signer, b64("123456789"))
    check("auth signs base64 of the INN", calls[0], ("sign", "MTIzNDU2Nzg5"))

    # envelope helpers
    check("extract_json unwraps data", extract_json({"data": {"json": {"a": 1}}}), {"a": 1})
    check("extract_field is case-insensitive", extract_field({"data": {"tosign": "X"}}, "toSign"), "X")
    check("extract_rows finds the list", extract_rows({"data": [{"id": "1"}]}), [{"id": "1"}])

    if failures:
        print("FAIL\n" + "\n".join(failures))
        return 1
    print("ok — signing order, join order, action branching and envelope helpers all hold")
    return 0


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selfcheck", action="store_true", help="run the offline flow assertions")
    a = p.parse_args()
    if a.selfcheck:
        raise SystemExit(_selfcheck())
    print(json.dumps({"flows": [
        "authenticate", "sign_public_offer", "create_and_sign", "sign_outgoing",
        "sign_incoming", "perform_action", "reject_document", "cancel_document", "poll_updated",
    ]}, indent=2))
