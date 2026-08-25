"""The Didox document machine (P7.a Stage 2 — W6).

Create a document, sign it, and act on what Didox says came back. Three things
here are load-bearing and none of them is obvious from the API docs:

**Signing is two round trips, and it has to be.** The bytes to sign are the JSON
Didox stores for the document, which the browser cannot know until the document
exists. So: `prepare_signature` fetches them and stashes them in Redis under a
single-use key; `submit_signature` takes the browser's PKCS#7, timestamps it,
joins it with the sender's when the document is incoming, and sends it. W5 learned
this the hard way on the public offer — a one-shot endpoint signed the PDF instead
of the JSON and produced a well-formed signature over the wrong content.

**The partner token never leaves the server.** The browser signs and posts
`pkcs7_64` + `signature_hex`; this side does `/v1/dsvs/timestamp` (which needs only
the partner token) and the send.

**Numbers are allocated before the POST.** `didox_documents` is committed with its
`number` and no `didox_id`, then the create runs. A create Didox accepted and we
timed out on therefore leaves a recoverable row rather than a silent gap, and a
retry reuses the number instead of burning a second one out of the seller's book.
"""

from __future__ import annotations

import base64
import datetime
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.domains.edi import onboarding
from app.domains.edi.models import (
    DOC_TYPE_CONTRACT,
    STATUS_ANNULLED_BY_TAX,
    STATUS_REJECTED,
    STATUS_SIGNED,
    DidoxDocument,
)
from app.domains.edi.payloads import JsonObject
from app.integrations.didox import (
    DidoxCreatedDocument,
    DidoxDocumentView,
    DidoxError,
    DidoxSignResult,
)
from app.services import storage_service

if TYPE_CHECKING:  # pragma: no cover
    import redis
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: Single-use stash for "the bytes we told the browser to sign". Same discipline as
#: the R3 contract challenge: short TTL, GETDEL, and a miss is `challenge_expired`
#: rather than a silent re-derivation that might produce different bytes.
_SIGN_PAYLOAD_KEY = "didox:signpayload:{doc_id}:{company_id}"
_SIGN_PAYLOAD_TTL = 300

#: Statuses that mean "no longer awaiting anyone" — see `models._DEAD_STATUSES`
#: for the deleted pair, which is a different kind of terminal.
_TERMINAL_BAD = (STATUS_REJECTED, STATUS_ANNULLED_BY_TAX)


class DidoxDocuments(Protocol):
    """The slice of `DidoxClient` this machine uses.

    Named rather than typed `Any` so a fake in a test has to keep up with the real
    surface — the signatures here are the contract, and drift shows up at type-check
    time instead of in a mock that silently accepts anything.
    """

    def create_document(
        self, doc_type: str, payload: JsonObject, *, locale: str = ..., user_key: str | None = ...
    ) -> DidoxCreatedDocument: ...
    def get_document(
        self, didox_id: str, *, owner: int = ..., user_key: str | None = ...
    ) -> DidoxDocumentView: ...
    def document_base64(self, didox_id: str, *, user_key: str | None = ...) -> str: ...
    def timestamp(self, pkcs7_64: str, signature_hex: str, *, user_key: str | None = ...) -> str: ...
    def join_signatures(
        self, signature1: str, signature2: str, *, user_key: str | None = ...
    ) -> str: ...
    def sign_document(
        self, didox_id: str, signature: str, *, user_key: str | None = ...
    ) -> DidoxSignResult: ...
    def send_document(
        self, didox_id: str, signature: str, *, user_key: str | None = ...
    ) -> DidoxSignResult: ...
    def archive(self, didox_id: str, *, user_key: str | None = ...) -> bytes: ...


class DocumentNotReady(Exception):
    """The document has no `didox_id` yet — its create never completed."""


class SignPayloadExpired(Exception):
    """The stashed bytes are gone; the browser must ask for them again."""


class OfferRequired(Exception):
    """Didox refused the send because the company never signed its public offer."""


@dataclass(frozen=True)
class SignOutcome:
    """What a send produced."""

    status: int
    activated: bool
    archive_sha256: str | None
    warning: JsonObject | None


def to_sign_bytes(document_json: JsonObject) -> str:
    """base64 of the document JSON, serialised the one way that reproduces.

    Compact separators and no ASCII escaping. The exact bytes matter twice over —
    the module signs them, and Didox verifies against its own copy — so this is a
    single function rather than an idiom repeated per call site.
    """
    payload = json.dumps(document_json, ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


# ── create ────────────────────────────────────────────────────────────────────


def create_document(
    db: Session,
    *,
    doc_type: str,
    subject_kind: str,
    subject_id: int,
    owner_company_id: int,
    partner_company_id: int | None,
    deal_id: int | None,
    number: str,
    doc_date: datetime.date,
    payload: JsonObject,
    created_by_user_account_id: int,
    user_key: str,
    tax_id: str,
    client: DidoxDocuments,
) -> DidoxDocument:
    """Record the row, THEN create it at Didox.

    That order is the recovery story: the row carries the number and is committed
    before the call, so a create we never saw the answer to is findable by
    ContractNo rather than lost.
    """
    onboarding.assert_live(db)
    row = DidoxDocument(
        doc_type=doc_type,
        subject_kind=subject_kind,
        subject_id=subject_id,
        owner_company_id=owner_company_id,
        partner_company_id=partner_company_id,
        deal_id=deal_id,
        number=number,
        doc_date=doc_date,
        payload=payload,
        created_by_user_account_id=created_by_user_account_id,
    )
    db.add(row)
    db.flush()

    try:
        created = client.create_document(doc_type, payload, user_key=user_key)
    except DidoxError as exc:
        row.last_error = exc.message[:500]
        db.flush()
        if exc.offer_not_signed:
            # Our record said the offer was signed and Didox disagrees. Correct
            # the record — the send is where that truth shows up.
            onboarding.note_offer_required(db, owner_company_id, tax_id)
            raise OfferRequired(str(owner_company_id)) from exc
        raise

    row.didox_id = created.didox_id
    row.didox_contract_id = created.didox_contract_id
    row.last_error = None
    db.flush()
    return row


# ── signing, round 1: what to sign ────────────────────────────────────────────


def prepare_signature(
    redis_client: redis.Redis[str] | None,
    row: DidoxDocument,
    *,
    company_id: int,
    user_key: str,
    client: DidoxDocuments,
) -> tuple[str, str]:
    """Return `(data_b64, mode)` — the bytes to sign and which flow applies.

    `mode` is `outgoing` when we are the document's owner and `incoming` when the
    counterparty sent it; they sign different things and the second needs a join
    afterwards, so the caller must not have to guess.
    """
    if not row.didox_id:
        raise DocumentNotReady(str(row.id))
    outgoing = row.owner_company_id == company_id
    if outgoing:
        view = client.get_document(row.didox_id, owner=1, user_key=user_key)
        data_b64 = to_sign_bytes(view.json_payload)
    else:
        # The incoming flow signs the document's own base64, then joins with the
        # sender's signature — which is why `documentBase64` exists at all.
        data_b64 = client.document_base64(row.didox_id, user_key=user_key)

    if redis_client is not None:
        redis_client.setex(
            _SIGN_PAYLOAD_KEY.format(doc_id=row.id, company_id=company_id),
            _SIGN_PAYLOAD_TTL,
            data_b64,
        )
    return data_b64, "outgoing" if outgoing else "incoming"


def _take_stashed_payload(
    redis_client: redis.Redis[str] | None, doc_id: int, company_id: int
) -> str:
    """Single use. A replay is an expiry, not a second signature."""
    if redis_client is None:
        raise SignPayloadExpired(str(doc_id))
    key = _SIGN_PAYLOAD_KEY.format(doc_id=doc_id, company_id=company_id)
    value = redis_client.getdel(key)
    if not value:
        raise SignPayloadExpired(str(doc_id))
    return str(value)


# ── signing, round 2: send it ─────────────────────────────────────────────────


def submit_signature(
    db: Session,
    redis_client: redis.Redis[str] | None,
    row: DidoxDocument,
    *,
    company_id: int,
    tax_id: str,
    pkcs7_64: str,
    signature_hex: str,
    user_key: str,
    client: DidoxDocuments,
) -> SignOutcome:
    """Timestamp, join if incoming, send — then react to the resulting status."""
    onboarding.assert_live(db)
    if not row.didox_id:
        raise DocumentNotReady(str(row.id))
    _take_stashed_payload(redis_client, row.id, company_id)

    signature = client.timestamp(pkcs7_64, signature_hex)
    outgoing = row.owner_company_id == company_id
    if not outgoing:
        # Incoming: theirs first, ours second. Reversed, the tax committee
        # rejects a PKCS#7 that is otherwise perfectly well formed.
        view = client.get_document(row.didox_id, owner=0, user_key=user_key)
        if view.to_sign:
            signature = client.join_signatures(view.to_sign, signature, user_key=user_key)

    try:
        # `POST /{id}/sign` for both directions.
        #
        # It answered 500 `Undefined variable $isDraft` on 21.08, which looked
        # like a broken endpoint and sent us to `PUT /{id}/send` instead. Once
        # the company's public offer was signed (25.08) that 500 disappeared and
        # `/send` started refusing a 007 outright — «Неподдерживаемый тип
        # документа». So the PHP error was a symptom of the unsigned offer, not a
        # second door: `send_document` stays on the client for the types that
        # want it, and nothing routes through it here.
        result = client.sign_document(row.didox_id, signature, user_key=user_key)
    except DidoxError as exc:
        row.last_error = exc.message[:500]
        db.flush()
        if exc.offer_not_signed:
            onboarding.note_offer_required(db, company_id, tax_id)
            raise OfferRequired(str(company_id)) from exc
        raise

    view = client.get_document(row.didox_id, owner=1, user_key=user_key)
    activated = apply_status(
        db, row, view.status, user_key=user_key, client=client
    )
    return SignOutcome(
        status=row.status,
        activated=activated,
        archive_sha256=row.provider_archive_sha256,
        warning=result.warning,
    )


# ── reacting to a status ──────────────────────────────────────────────────────


def apply_status(
    db: Session,
    row: DidoxDocument,
    status: int | None,
    *,
    user_key: str,
    client: DidoxDocuments,
) -> bool:
    """Move the row to `status` and do whatever that transition earns.

    **Forward-only.** The poller's cursor has day granularity and is deliberately
    overlapped, so a stale page reporting an earlier status than we already hold is
    routine — and applying it would undo an activation. Returns whether a contract
    was activated by this call.

    Statuses `4` (rejected) and `50` (annulled by the tax committee) are recorded
    and alerted, and change no state of ours: `active` is terminal, a deal may
    already be riding on it, and a silent move to some new terminal state would
    leave that deal without footing. Those are legal events for a human.
    """
    from app.core.time import utcnow  # noqa: PLC0415

    if status is None or status < row.status:
        return False

    row.status = status
    row.status_synced_at = utcnow()
    db.flush()

    if status in _TERMINAL_BAD:
        logger.warning(
            "didox.document.terminal",
            extra={"doc_id": row.id, "didox_id": row.didox_id, "status": status},
        )
        return False

    if status != STATUS_SIGNED:
        return False
    return _on_signed(db, row, user_key=user_key, client=client)


def _on_signed(
    db: Session, row: DidoxDocument, *, user_key: str, client: DidoxDocuments
) -> bool:
    """Fetch the archive ONCE, then activate the contract if this is a договор."""
    from app.core.time import utcnow  # noqa: PLC0415

    if row.provider_archive_sha256 is None and row.didox_id:
        try:
            blob = client.archive(row.didox_id, user_key=user_key)
            path, sha = storage_service.store_didox_archive(str(row.didox_id), blob)
        except Exception as exc:  # noqa: BLE001 — a missing archive must not block activation
            # The document IS signed either way; the archive is evidence we can
            # fetch again later. Losing the transition over it would be worse.
            logger.warning(
                "didox.archive.failed", extra={"doc_id": row.id, "error": str(exc)}
            )
        else:
            row.provider_archive_path = path
            row.provider_archive_sha256 = sha
            row.archived_at = utcnow()
            db.flush()

    if row.doc_type != DOC_TYPE_CONTRACT or row.subject_kind != "contract":
        return False
    return _activate_contract(db, row)


def _activate_contract(db: Session, row: DidoxDocument) -> bool:
    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.domains.contracts.models import Contract  # noqa: PLC0415

    contract = db.get(Contract, row.subject_id)
    if contract is None:
        return False
    try:
        contract_service.activate_from_provider(
            db,
            contract,
            contract_service.ProviderEvidence(
                provider="didox",
                doc_id=str(row.didox_id),
                archive_path=row.provider_archive_path or "",
                archive_sha256=row.provider_archive_sha256 or "",
            ),
        )
    except (contract_service.WrongRail, contract_service.InvalidContractTransition) as exc:
        logger.warning(
            "didox.activate.refused", extra={"doc_id": row.id, "error": str(exc)}
        )
        return False
    return True
