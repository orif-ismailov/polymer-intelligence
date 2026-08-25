"""Portal Didox onboarding + session endpoints (P7.a Stage 2 — W5). Under /api/v1.

Company-scoped through `company_or_404`, so a non-member gets 404 rather than 403 —
the same rule the rest of the portal follows: a stranger learns nothing about which
company ids exist.

The partner token never appears here. The browser signs, posts `pkcs7_64` +
`signature_hex`, and THIS side does the `/v1/dsvs/timestamp` round trip and the
Didox call — which is the whole reason the timestamp leg needs only the partner
token and not a `user-key`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404
from app.core.db import get_db
from app.core.redis import get_redis
from app.domains.accounts.models import UserAccount
from app.domains.edi import onboarding, session
from app.domains.edi import service as edi_service
from app.domains.edi.models import DidoxCompany, DidoxDocument
from app.domains.edi.payloads import DocumentLine
from app.domains.edi.schemas import (
    DidoxContractDocumentIn,
    DidoxContractLineIn,
    DidoxContractPrefillOut,
    DidoxDocumentOut,
    DidoxOfferIn,
    DidoxOfferOut,
    DidoxSessionOut,
    DidoxSignatureIn,
    DidoxSignPayloadOut,
    DidoxSignupIn,
    DidoxStatusOut,
)
from app.integrations.didox import DidoxError, ProviderUnavailable, get_didox_client

if TYPE_CHECKING:  # pragma: no cover
    # Annotation only: importing the contracts model at module scope would tie
    # this router's import order to that domain's for nothing.
    from app.domains.contracts.models import Contract

router = APIRouter(prefix="/portal/companies", tags=["portal-didox"])

_DISABLED = "didox_disabled"


def _guard(db: Session) -> None:
    """Actions only. Reading a status on the stub rail is fine; acting is not."""
    try:
        onboarding.assert_live(db)
    except onboarding.ChannelDisabled as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_DISABLED) from exc


def _provider_error(exc: DidoxError) -> HTTPException:
    """Didox said our request was wrong. Two of its 4xx answers are actionable."""
    if exc.offer_not_signed:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="didox_offer_required")
    if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY and "not registered" in exc.message.lower():
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="didox_not_registered")
    # Everything else: pass THEIR sentence through verbatim. It is routinely the
    # only actionable thing in the exchange — «ИНН/ПИНФЛ заказчика некорректный.
    # ИНН/ПИНФЛ: 562353400» tells a seller exactly what is wrong, and a UI that
    # renders it as «не удалось подписать» throws that away. `description` is
    # their own remedy text when they have one.
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "error": "didox_rejected",
            "message": exc.message,
            "description": exc.description,
            "trace_id": exc.trace_id,
        },
    )


class _TinRegistry(Protocol):
    """The one read this check needs — `info_by_tin` off the Didox gateway."""

    def info_by_tin(self, tin: str) -> object | None: ...


def _counterparty_blocker(registry: _TinRegistry, tax_id: str | None) -> str | None:
    """Is the BUYER a company Didox will accept on a document?

    Answered here rather than discovered at `/sign`, because the refusal
    (`ИНН/ПИНФЛ заказчика некорректный`) arrives only AFTER the seller has loaded
    a key, typed its password and produced a timestamped signature. One registry
    read moves it to the screen where every other blocker already lives.

    A lookup that cannot answer returns nothing: Didox being down is our outage,
    and reporting it as "this counterparty is invalid" would be a finding about a
    real business — the rule `StubGovRegistryClient` already refuses to break.
    """
    if not tax_id:
        return None
    try:
        found = registry.info_by_tin(tax_id)
    except Exception:  # noqa: BLE001 — any provider failure is silence, not a verdict
        return None
    return None if found is not None else "counterparty_unknown"


class _IkpuBaskets(Protocol):
    """`class_packages` — the per-company list of declared ИКПУ."""

    def class_packages(
        self,
        tax_id: str,
        class_code: str,
        *,
        locale: str = ...,
        user_key: str | None = ...,
    ) -> list[tuple[str, str]]: ...


def _counterparty_ikpu_blocker(
    baskets: _IkpuBaskets, tax_id: str | None, class_code: str | None
) -> str | None:
    """Has the BUYER declared this ИКПУ in their own Didox account?

    The gate behind the tax id. With a counterparty Didox recognises, `/sign`
    answers `[<code>] не включены в список избранных ИКПУ!` — and the list it
    means is theirs, not ours: `class_packages` confirms the code for the seller
    and refuses it for the buyer with «танланган МХИКлар рўйхатида мавжуд эмас».

    We cannot fill someone else's basket, so this can only ever be shown, never
    fixed here — which is exactly why it belongs beside the other blockers rather
    than after a password. Same rule as everywhere on this screen: a provider
    that cannot answer says nothing.
    """
    if not tax_id or not class_code:
        return None
    try:
        baskets.class_packages(tax_id, class_code)
    except DidoxError:
        return "counterparty_ikpu_missing"
    except Exception:  # noqa: BLE001 — an outage is not a verdict
        return None
    return None


@router.get("/{company_id}/didox/status", response_model=DidoxStatusOut)
def didox_status(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> DidoxStatusOut:
    """Where this company stands. Never calls Didox — the state is ours to hold."""
    company = company_or_404(db, account, company_id)
    disabled = onboarding.channel_state(db)
    if disabled is not None:
        return DidoxStatusOut(state=disabled, has_session=False)
    row = db.get(DidoxCompany, company.id)
    return DidoxStatusOut(
        state=onboarding.state_of(row),
        has_session=session.cached_user_key(redis_client, company.tax_id) is not None,
    )


@router.post("/{company_id}/didox/session", response_model=DidoxSessionOut)
def didox_session(
    company_id: int,
    body: DidoxSignatureIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> DidoxSessionOut:
    """Mint a `user-key` from a browser signature over the company's INN.

    Succeeding proves the Didox account exists, which is the only signal we get
    for the signup step when a company registered on Didox's own site.
    """
    company = company_or_404(db, account, company_id)
    _guard(db)
    try:
        session.mint_user_key(
            redis_client,
            company,
            pkcs7_64=body.pkcs7_64,
            signature_hex=body.signature_hex,
            client=get_didox_client(),
        )
    except DidoxError as exc:
        raise _provider_error(exc) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="didox_unavailable"
        ) from exc
    row = onboarding.note_signed_in(db, company.id, company.tax_id)
    db.commit()
    return DidoxSessionOut(state=onboarding.state_of(row))


@router.post("/{company_id}/didox/signup", response_model=DidoxSessionOut)
def didox_signup(
    company_id: int,
    body: DidoxSignupIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> DidoxSessionOut:
    """Create the company's Didox account (step 1 of 2)."""
    company = company_or_404(db, account, company_id)
    _guard(db)
    try:
        token = onboarding.register(
            db,
            company.id,
            company.tax_id,
            pkcs7_64=body.pkcs7_64,
            signature_hex=body.signature_hex,
            email=body.email,
            mobile=body.mobile,
            password=body.password,
            client=get_didox_client(),
        )
    except DidoxError as exc:
        raise _provider_error(exc) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="didox_unavailable"
        ) from exc
    # Signup hands back a usable key — cache it so the next step needs no second
    # signature from a user who has their card in the reader right now.
    session.cache_user_key(redis_client, company.tax_id, token)
    row = db.get(DidoxCompany, company.id)
    db.commit()
    return DidoxSessionOut(state=onboarding.state_of(row))


@router.get("/{company_id}/didox/offer", response_model=DidoxOfferOut)
def didox_offer(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> DidoxOfferOut:
    """The public offer PDF to sign (step 2 of 2)."""
    company = company_or_404(db, account, company_id)
    _guard(db)
    try:
        user_key = session.require_user_key(redis_client, company)
        return DidoxOfferOut(
            document_b64=onboarding.offer_to_sign(
                db, tax_id=company.tax_id, user_key=user_key, client=get_didox_client()
            )
        )
    except session.UserKeyRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="didox_session_required"
        ) from exc
    except DidoxError as exc:
        raise _provider_error(exc) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="didox_unavailable"
        ) from exc


@router.post("/{company_id}/didox/offer", response_model=DidoxSessionOut)
def didox_accept_offer(
    company_id: int,
    body: DidoxOfferIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> DidoxSessionOut:
    """Sign the public offer. Until this succeeds the first SEND fails 422."""
    company = company_or_404(db, account, company_id)
    _guard(db)
    try:
        user_key = session.require_user_key(redis_client, company)
        onboarding.accept_offer(
            db,
            company.id,
            company.tax_id,
            pkcs7_64=body.pkcs7_64,
            signature_hex=body.signature_hex,
            user_key=user_key,
            client=get_didox_client(),
        )
    except session.UserKeyRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="didox_session_required"
        ) from exc
    except DidoxError as exc:
        raise _provider_error(exc) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="didox_unavailable"
        ) from exc
    row = db.get(DidoxCompany, company.id)
    db.commit()
    return DidoxSessionOut(state=onboarding.state_of(row))


# ── documents: the two-round-trip signature ───────────────────────────────────


def _document_or_404(db: Session, account: UserAccount, document_id: int) -> DidoxDocument:
    """Resolve a document the acting account's company is a party to.

    Either side may sign, so membership of the owner OR the partner company is
    enough. A stranger gets 404, never 403.
    """
    row = db.get(DidoxDocument, document_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document_not_found")
    for company_id in (row.owner_company_id, row.partner_company_id):
        if company_id is None:
            continue
        try:
            company_or_404(db, account, company_id)
        except HTTPException:
            continue
        else:
            return row
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document_not_found")


def _acting_company_id(db: Session, account: UserAccount, row: DidoxDocument) -> int:
    for company_id in (row.owner_company_id, row.partner_company_id):
        if company_id is None:
            continue
        try:
            company_or_404(db, account, company_id)
        except HTTPException:
            continue
        else:
            return company_id
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document_not_found")


@router.post("/documents/{document_id}/sign-payload", response_model=DidoxSignPayloadOut)
def didox_sign_payload(
    document_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> DidoxSignPayloadOut:
    """Round 1: the exact bytes to sign, stashed single-use for round 2.

    The browser cannot derive these — they are the JSON Didox holds for the
    document — so they are fetched here and pinned, rather than re-derived on
    submit where they might come back different.
    """
    row = _document_or_404(db, account, document_id)
    _guard(db)
    company_id = _acting_company_id(db, account, row)
    company = company_or_404(db, account, company_id)
    try:
        user_key = session.require_user_key(redis_client, company)
        data_b64, mode = edi_service.prepare_signature(
            redis_client, row, company_id=company_id, user_key=user_key,
            client=get_didox_client(),
        )
    except session.UserKeyRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="didox_session_required"
        ) from exc
    except edi_service.DocumentNotReady as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="document_not_created"
        ) from exc
    except DidoxError as exc:
        raise _provider_error(exc) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="didox_unavailable"
        ) from exc
    return DidoxSignPayloadOut(data_b64=data_b64, mode=mode)


@router.post("/documents/{document_id}/sign", response_model=DidoxDocumentOut)
def didox_sign_document(
    document_id: int,
    body: DidoxSignatureIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> DidoxDocumentOut:
    """Round 2: timestamp, join if incoming, send — and act on the new status."""
    row = _document_or_404(db, account, document_id)
    _guard(db)
    company_id = _acting_company_id(db, account, row)
    company = company_or_404(db, account, company_id)
    try:
        user_key = session.require_user_key(redis_client, company)
        outcome = edi_service.submit_signature(
            db, redis_client, row,
            company_id=company_id, tax_id=company.tax_id,
            pkcs7_64=body.pkcs7_64, signature_hex=body.signature_hex,
            user_key=user_key, client=get_didox_client(),
        )
    except session.UserKeyRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="didox_session_required"
        ) from exc
    except edi_service.SignPayloadExpired as exc:
        # Same contract as the R3 contract challenge: the stash is single use, so
        # a replay reads as an expiry and the browser asks for fresh bytes.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="challenge_expired"
        ) from exc
    except edi_service.OfferRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="didox_offer_required"
        ) from exc
    except DidoxError as exc:
        raise _provider_error(exc) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="didox_unavailable"
        ) from exc
    db.commit()
    return DidoxDocumentOut(
        id=row.id, doc_type=row.doc_type, number=row.number, status=outcome.status,
        didox_id=row.didox_id, activated=outcome.activated,
        archive_sha256=outcome.archive_sha256, warning=outcome.warning,
    )


# ── the contract → 007 door ───────────────────────────────────────────────────


def _contract_or_404(db: Session, contract_id: int, company_id: int) -> Contract:
    """The contract, only if the acting company is a party to it."""
    from app.domains.contracts.models import Contract  # noqa: PLC0415

    contract = db.get(Contract, contract_id)
    if contract is None or company_id not in {
        contract.initiator_company_id,
        contract.counterparty_company_id,
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contract_not_found")
    return contract


def _prefill(db: Session, contract: Contract, company_id: int) -> DidoxContractPrefillOut:
    """What the seller is about to send — and every reason it would be refused.

    Collected rather than raised one at a time: a seller who has to discover
    three missing things in three round trips, each after loading a key, will
    reasonably conclude the feature is broken.
    """
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.edi import contract_docs  # noqa: PLC0415
    from app.domains.edi.payloads import IkpuMissing  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415

    deal = contract_docs._linked_deal(db, contract)  # noqa: SLF001
    offer = contract_docs._linked_offer(db, contract, deal)  # noqa: SLF001
    blockers: list[str] = []
    try:
        seller_id, buyer_id = contract_docs.resolve_parties(contract, deal=deal, offer=offer)
    except contract_docs.PartyMismatch:
        seller_id, buyer_id = contract.initiator_company_id, contract.counterparty_company_id
        blockers.append("party_mismatch")

    if contract.signing_provider != "didox":
        blockers.append("wrong_rail")
    if contract.status != ContractStatus.pending_signatures:
        blockers.append("not_ready")
    if company_id != seller_id:
        blockers.append("not_seller")

    lines: list[DidoxContractLineIn] = []
    try:
        lines = [
            DidoxContractLineIn(
                name=line.name, count=line.count, price=line.price, vat_rate=line.vat_rate
            )
            for line in contract_docs.suggested_lines(contract, offer)
        ]
    except IkpuMissing:
        blockers.append("ikpu_missing")

    for party_id in (seller_id, buyer_id):
        company = db.get(Company, party_id)
        if company is None:
            continue
        try:
            contract_docs.party_from_company(db, company)
        except contract_docs.SignerIdentityMissing:
            blockers.append(f"signer_identity_missing:{party_id}")

    existing = contract_docs._existing_document(db, contract)  # noqa: SLF001
    seller = db.get(Company, seller_id)
    buyer = db.get(Company, buyer_id)

    # Only worth a network call while there is still a document to create, and
    # only for the party Didox judges — us it already knows, or we could not have
    # minted a user-key.
    if existing is None and buyer is not None:
        client = get_didox_client()
        unknown = _counterparty_blocker(client, buyer.tax_id)
        if unknown:
            blockers.append(unknown)
        elif offer is not None:
            # Only worth asking once the counterparty is real: an unknown ИНН has
            # no basket to look in, and two blockers for one cause read as two.
            missing = _counterparty_ikpu_blocker(client, buyer.tax_id, offer.ikpu_code)
            if missing:
                blockers.append(missing)

    return DidoxContractPrefillOut(
        contract_id=int(contract.id),
        seller_company_id=int(seller_id),
        buyer_company_id=int(buyer_id),
        seller_name=(seller.legal_name or seller.tax_id) if seller else None,
        buyer_name=(buyer.legal_name or buyer.tax_id) if buyer else None,
        document_id=int(existing.id) if existing else None,
        lines=lines,
        blockers=blockers,
    )


@router.get(
    "/{company_id}/didox/contracts/{contract_id}/document",
    response_model=DidoxContractPrefillOut,
)
def didox_contract_prefill(
    company_id: int,
    contract_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> DidoxContractPrefillOut:
    """Everything the create needs, plus what is missing — a plain read."""
    company_or_404(db, account, company_id)
    contract = _contract_or_404(db, contract_id, company_id)
    return _prefill(db, contract, company_id)


@router.post(
    "/{company_id}/didox/contracts/{contract_id}/document",
    response_model=DidoxDocumentOut,
    status_code=status.HTTP_201_CREATED,
)
def didox_create_contract_document(
    company_id: int,
    contract_id: int,
    body: DidoxContractDocumentIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> DidoxDocumentOut:
    """Create the «Договор НК» 007 for this contract at Didox.

    Idempotent: a contract already has at most one live document (partial unique
    index), and a second press returns the first rather than a 409 nobody can act
    on.
    """
    from app.core.time import utcnow  # noqa: PLC0415
    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.domains.edi import contract_docs  # noqa: PLC0415
    from app.domains.edi.payloads import IkpuMissing  # noqa: PLC0415

    company = company_or_404(db, account, company_id)
    contract = _contract_or_404(db, contract_id, company_id)
    _guard(db)

    lines = [
        DocumentLine(
            ord_no=index,
            name=line.name,
            catalog_code="",
            catalog_name="",
            package_code="",
            package_name="",
            count=line.count,
            price=line.price,
            vat_rate=line.vat_rate,
        )
        for index, line in enumerate(body.lines, start=1)
    ]
    try:
        user_key = session.require_user_key(redis_client, company)
        row = contract_docs.create_for_contract(
            db,
            contract,
            acting_company_id=company_id,
            account_id=int(account.id),
            # An empty list means "use the prefill" — the seller confirmed it
            # unchanged, and re-deriving is how the ИКПУ stays the offer's.
            lines=None if not lines else _with_ikpu(db, contract, lines),
            user_key=user_key,
            client=get_didox_client(),
            today=utcnow().date(),
        )
    except session.UserKeyRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="didox_session_required"
        ) from exc
    except contract_service.WrongRail as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="wrong_rail") from exc
    except contract_docs.NotReadyToSend as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="not_ready") from exc
    except contract_docs.PartyMismatch as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="not_seller") from exc
    except contract_docs.SignerIdentityMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "signer_identity_missing", "company_id": exc.company_id},
        ) from exc
    except IkpuMissing as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ikpu_missing") from exc
    except contract_docs.EmptyContractBody as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="empty_body") from exc
    except edi_service.OfferRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="didox_offer_required"
        ) from exc
    except DidoxError as exc:
        raise _provider_error(exc) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="didox_unavailable"
        ) from exc

    db.commit()
    return DidoxDocumentOut(
        id=row.id,
        doc_type=row.doc_type,
        number=row.number,
        status=row.status,
        didox_id=row.didox_id,
    )


def _with_ikpu(
    db: Session, contract: Contract, lines: list[DocumentLine]
) -> list[DocumentLine]:
    """Stamp the offer's tax classification onto seller-edited lines.

    The seller may correct a name, a quantity or a price; they may not invent an
    ИКПУ, because that code is chosen once on the offer and reused by every
    document it backs.
    """
    import dataclasses  # noqa: PLC0415

    from app.domains.edi import contract_docs  # noqa: PLC0415

    deal = contract_docs._linked_deal(db, contract)  # noqa: SLF001
    offer = contract_docs._linked_offer(db, contract, deal)  # noqa: SLF001
    [template] = contract_docs.suggested_lines(contract, offer)
    return [
        dataclasses.replace(
            line,
            catalog_code=template.catalog_code,
            catalog_name=template.catalog_name,
            package_code=template.package_code,
            package_name=template.package_name,
            origin=template.origin,
        )
        for line in lines
    ]
