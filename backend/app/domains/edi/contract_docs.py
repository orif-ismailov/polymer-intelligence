"""Turn one of OUR contracts into a Didox «Договор НК» 007 (P7.a Stage 2).

This is the step the rail was missing. Everything downstream existed —
`edi_service.create_document`, the two-round-trip signing, the poller, the staff
surface — but nothing ever called it, so `contracts.signing_provider='didox'` was
a flag with no consequence and the portal's Didox branch could never light up.

Three decisions are worth stating, because each has a wrong answer that looks
reasonable:

**The owner is the SELLER, not the initiator.** Whoever pressed «создать» is a UI
fact; who sells is a tax fact. The ЭСФ that follows is issued by the seller and
quotes this document's number, so getting this backwards produces a pair the
roaming centre refuses — after both parties have signed.

**The prose comes from the contract we already rendered.** Didox shows `Parts` as
the body of the document, and re-authoring it here would create a second source of
truth for text that both parties are about to sign. We lift the sections out of
the same HTML the PDF was rendered from.

**Nothing is invented.** A missing signer identity, a missing ИКПУ or an empty
body raises rather than defaulting: every one of those fields ends up on a
document that reaches my.soliq.uz.
"""

from __future__ import annotations

import datetime
import html
import re
from typing import TYPE_CHECKING, Protocol

from app.domains.edi.payloads import (
    DocumentLine,
    JsonObject,
    PartyRequisites,
    build_contract_007,
)
from app.domains.edi.service import DidoxDocuments

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

    from app.domains.companies.models import Company
    from app.domains.contracts.models import Contract
    from app.domains.deals.models import Deal
    from app.domains.edi.models import DidoxDocument
    from app.domains.marketplace.models import SellerOffer
    from app.integrations.didox.client import DidoxVatStatus


class ContractGateway(DidoxDocuments, Protocol):
    """`DidoxDocuments` plus the two reads this assembler needs of its own.

    `vatRegStatus` is date- and role-sensitive, so it is read per document rather
    than cached on the company — which makes it part of building a document, not
    part of sending one. `info_by_tin` is the state registry, and it is what
    describes the BUYER: see `party_from_registry`.
    """

    def vat_reg_status(
        self,
        tax_id: str,
        *,
        document_date: str | None = ...,
        is_seller: bool | None = ...,
        user_key: str | None = ...,
    ) -> DidoxVatStatus | None: ...

    def info_by_tin(self, tin: str) -> object | None: ...


class PartyMismatch(Exception):
    """The offer's seller is not a party to this contract."""


class EmptyContractBody(Exception):
    """A contract with no terms or no goods is not a contract we can send."""


class SignerIdentityMissing(Exception):
    """`Owner.FizTin`/`Fio` are mandatory and only E-IMZO confirmation supplies them.

    Carries the company id so the caller can point the user at the right
    «подтвердите личность ЭЦП» screen rather than at a 422.
    """

    def __init__(self, company_id: int) -> None:
        super().__init__(f"company {company_id} has no confirmed signer identity")
        self.company_id = company_id


def resolve_parties(
    contract: Contract,
    *,
    deal: Deal | None = None,
    offer: SellerOffer | None = None,
) -> tuple[int, int]:
    """`(seller_company_id, buyer_company_id)` for this contract.

    In order of authority: the deal knows both sides explicitly; failing that the
    offer's owner is the seller; failing both we assume the initiator sells and
    say so on screen before anything is created.
    """
    parties = {contract.initiator_company_id, contract.counterparty_company_id}
    if deal is not None:
        return int(deal.seller_company_id), int(deal.buyer_company_id)
    if offer is not None and offer.company_id is not None:
        # `seller_offers.company_id` is nullable — the Telegram-origin offers
        # predate portal companies entirely, and one of those can back no
        # provider document at all.
        seller = int(offer.company_id)
        if seller not in parties:
            raise PartyMismatch(
                f"offer {getattr(offer, 'id', '?')} belongs to company {seller}, "
                f"which is not a party to contract {getattr(contract, 'id', '?')}"
            )
        buyer = next(pid for pid in parties if pid != seller)
        return seller, buyer
    return int(contract.initiator_company_id), int(contract.counterparty_company_id)


_TAG = re.compile(r"<[^>]+>")
_SECTION = re.compile(r"<h2[^>]*>(?P<title>.*?)</h2>(?P<body>.*?)(?=<h2|\Z)", re.S | re.I)
_SPACE = re.compile(r"\s+")


def _plain(fragment: str) -> str:
    """Markup out, entities decoded, whitespace collapsed.

    The text is prose on a tax document, so a stray `<b>` or `&laquo;` is not a
    cosmetic problem — it is what the counterparty reads and signs.
    """
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", fragment))).strip()


#: A leading ordinal: `1.` · `2)` · `1.2.` — the position, not the name.
#:
#: The trailing `.`/`)` is REQUIRED. Without it a bare number is not a numbering
#: at all: «2026 год: особые условия» would lose its year, and no heading is worth
#: that risk to save one edge case.
_LEADING_ORDINAL = re.compile(r"^\s*\d+(?:\.\d+)*\s*[.)]\s+")


def _strip_leading_ordinal(title: str) -> str:
    """Drop the section number, because on their form the number is theirs.

    Didox prefixes `ordno` when it prints, so «1. Стороны» came out as
    «1. 1. Стороны». Ours is the one to go: their order IS `ordno`, and a number
    of ours that disagreed with it would be worse than a duplicated one.

    Only a LEADING ordinal, and never the whole title — «Приложение №2» keeps its
    number because that is part of the name, and a heading that is nothing but a
    number is left alone rather than blanked.
    """
    stripped = _LEADING_ORDINAL.sub("", title, count=1)
    return stripped if stripped else title


def sections_from_html(rendered_html: str) -> list[tuple[str, str]]:
    """`(title, body)` per `<h2>` of the rendered contract, in document order.

    `<h1>` is the document's own title and is carried by `ContractName`, so it is
    deliberately not a section.
    """
    out: list[tuple[str, str]] = []
    for match in _SECTION.finditer(rendered_html):
        title = _strip_leading_ordinal(_plain(match.group("title")))
        body = _plain(match.group("body"))
        if title or body:
            out.append((title, body))
    return out


def build_body(
    *,
    number: str,
    date: datetime.date,
    expires_on: datetime.date,
    title: str,
    seller: PartyRequisites,
    buyer: PartyRequisites,
    lines: list[DocumentLine],
    sections: list[tuple[str, str]],
    place: str = "г. Ташкент",
) -> JsonObject:
    """The 007 body for this contract — refusing anything hollow."""
    if not sections:
        raise EmptyContractBody("contract has no sections to send")
    if not lines:
        raise EmptyContractBody("contract has no product lines")
    return build_contract_007(
        number=number,
        date=date,
        expires_on=expires_on,
        place=place,
        title=title,
        seller=seller,
        buyer=buyer,
        lines=lines,
        parts=sections,
    )


def party_from_company(
    db: Session,
    company: Company,
    *,
    vat_reg_code: str | None = None,
    vat_reg_status: int | None = None,
    require_identity: bool = True,
) -> PartyRequisites:
    """Assemble one side of the document from what we already hold.

    Bank details and address come from the same helper the PDF uses, so the two
    renderings of the same contract cannot disagree.

    `require_identity` is asymmetric on purpose, and the asymmetry is the point.

    **The seller must be identified.** They are `Owner`, they sign here, and
    `Owner.FizTin`/`Fio` are the subject of that signature. We hold their
    confirmation because they confirmed it in this cabinet.

    **The buyer need not be.** Probed live on 25.08.2026: Didox accepts a 007
    whose `Clients[0].FizTin`/`Fio` are empty. Requiring them blocked the case
    that matters — a counterparty who is not our user, has no
    `company_person_data` here and never will, yet can receive and sign the
    document perfectly well at their own operator. It also implied we had
    verified an identity we never saw: on this rail the other side's PKCS#7 never
    reaches us, which is the same reason no `contract_signatures` row is written
    for them. Absent stays absent — a placeholder person on a document that
    reaches my.soliq.uz would be a false statement.
    """
    from app.core.crypto import decrypt_pii  # noqa: PLC0415
    from app.domains.contracts.eimzo_models import CompanyPersonData  # noqa: PLC0415
    from app.domains.contracts.service import _requisites  # noqa: PLC0415

    requisites = _requisites(db, company)
    person = (
        db.query(CompanyPersonData)
        .filter(CompanyPersonData.company_id == company.id)
        .order_by(CompanyPersonData.id.desc())
        .first()
    )
    if person is None:
        raise SignerIdentityMissing(int(company.id))
    try:
        fio = decrypt_pii(person.full_name_enc)
        pinfl = decrypt_pii(person.pinfl_enc)
    except Exception as exc:  # noqa: BLE001 — undecryptable PII is a missing identity
        raise SignerIdentityMissing(int(company.id)) from exc
    if not fio or not pinfl:
        raise SignerIdentityMissing(int(company.id))

    return PartyRequisites(
        tin=str(requisites["inn"]),
        name=str(requisites["legal_name"]),
        address=str(requisites["address"]) or None,
        oked=_oked_for(db, company),
        account=str(requisites["bank_account"]) or None,
        bank_mfo=str(requisites["bank_mfo"]) or None,
        fiz_tin=pinfl,
        fio=fio,
        director=str(requisites["director"]) or None,
        accountant=str(requisites["director"]) or None,
        vat_reg_code=vat_reg_code,
        vat_reg_status=vat_reg_status,
    )


class CounterpartyNotInRegistry(Exception):
    """The tax registry cannot describe the buyer, so no document can name them."""

    def __init__(self, tax_id: str) -> None:
        super().__init__(f"tax registry has no usable record for {tax_id}")
        self.tax_id = tax_id


class _TinRegistry(Protocol):
    def info_by_tin(self, tin: str) -> object | None: ...


def party_from_registry(registry: _TinRegistry, tax_id: str) -> PartyRequisites:
    """The BUYER's block, taken from the state registry rather than from us.

    Learned live on 27.08.2026, after two days spent on the opposite assumption:
    `GET /v1/utils/info/{tin}` returns `directorPinfl` and `director` for any
    company in the registry, so the counterparty's signer does NOT have to be
    someone who confirmed their identity in our cabinet. That was the belief that
    made a Didox document impossible for anyone who is not our own user, and it
    was simply wrong.

    Using the registry here is also the more correct source, not merely the
    available one: this document is checked against the tax authority's own
    record of that company, so the tax authority's record is what should be on
    it. Our `company_person_data` says who signs in OUR cabinet, which on this
    rail the buyer never does.

    Refuses rather than degrades. A registry that does not know the company, or
    knows it without a signer, produces exactly the 422 Didox answers AFTER the
    seller has typed their key password — so it is turned into a stop here.
    """
    try:
        info = registry.info_by_tin(tax_id)
    except Exception as exc:  # noqa: BLE001 — down or absent are the same to a document
        raise CounterpartyNotInRegistry(tax_id) from exc
    if info is None:
        raise CounterpartyNotInRegistry(tax_id)

    pinfl = getattr(info, "director_pinfl", None)
    fio = getattr(info, "director", None)
    if not pinfl or not fio:
        raise CounterpartyNotInRegistry(tax_id)

    address = (getattr(info, "address", None) or "").strip() or None
    return PartyRequisites(
        tin=tax_id,
        name=str(getattr(info, "name", None) or tax_id),
        address=address,
        oked=getattr(info, "oked", None),
        account=getattr(info, "bank_account", None),
        bank_mfo=getattr(info, "bank_mfo", None),
        fiz_tin=str(pinfl),
        fio=str(fio),
        director=str(fio),
        accountant=str(fio),
        vat_reg_code=getattr(info, "vat_reg_code", None),
        vat_reg_status=getattr(info, "vat_reg_status", None),
    )


def _oked_for(db: Session, company: Company) -> str | None:
    """OKED off the latest company registry snapshot, or nothing.

    Never guessed: an invented activity code on a document that reaches the tax
    authority is worse than an absent one, which Didox accepts as an empty string.
    """
    from app.domains.verification.registry_models import RegistrySnapshot  # noqa: PLC0415

    snapshot = (
        db.query(RegistrySnapshot)
        .filter(RegistrySnapshot.company_id == company.id, RegistrySnapshot.kind == "company")
        .order_by(RegistrySnapshot.id.desc())
        .first()
    )
    if snapshot is None or not isinstance(snapshot.payload, dict):
        return None
    oked = snapshot.payload.get("oked")
    return str(oked) if oked else None


# ── the door itself ───────────────────────────────────────────────────────────


class NotReadyToSend(Exception):
    """The contract has not reached the point where a provider document is due."""


def _linked_deal(db: Session, contract: Contract) -> Deal | None:
    from app.domains.deals.models import Deal  # noqa: PLC0415

    return db.query(Deal).filter(Deal.contract_id == contract.id).one_or_none()


def _linked_offer(db: Session, contract: Contract, deal: Deal | None) -> SellerOffer | None:
    from app.domains.marketplace.models import SellerOffer  # noqa: PLC0415

    offer_id = contract.offer_id or (deal.offer_id if deal is not None else None)
    return db.get(SellerOffer, offer_id) if offer_id else None


def _existing_document(db: Session, contract: Contract) -> DidoxDocument | None:
    from app.domains.edi.models import DidoxDocument  # noqa: PLC0415

    return (
        db.query(DidoxDocument)
        .filter(
            DidoxDocument.subject_kind == "contract",
            DidoxDocument.subject_id == contract.id,
            DidoxDocument.status.notin_([5, 55]),
        )
        .order_by(DidoxDocument.id.desc())
        .first()
    )


def suggested_lines(contract: Contract, offer: SellerOffer | None) -> list[DocumentLine]:
    """One line, from the contract's own variables plus the offer's ИКПУ.

    The quantity and price are the CONTRACT's — they were negotiated and may
    differ from the listing — while the tax classification can only come from the
    offer, which is where the seller chose it once.
    """
    import decimal  # noqa: PLC0415

    from app.domains.edi.payloads import line_from_offer  # noqa: PLC0415

    variables = contract.variables if isinstance(contract.variables, dict) else {}

    def _number(key: str, fallback: str) -> decimal.Decimal:
        raw = str(variables.get(key) or fallback).replace(",", ".").replace(" ", "")
        try:
            return decimal.Decimal(raw)
        except decimal.InvalidOperation:
            return decimal.Decimal(fallback)

    name = str(variables.get("product") or contract.title)
    return [
        line_from_offer(
            offer,
            ord_no=1,
            name=name,
            count=_number("qty", "1"),
            price=_number("price", "0"),
        )
    ]


def create_for_contract(
    db: Session,
    contract: Contract,
    *,
    acting_company_id: int,
    account_id: int,
    lines: list[DocumentLine] | None,
    user_key: str,
    client: ContractGateway,
    today: datetime.date,
    term_days: int = 365,
) -> DidoxDocument:
    """Create (or return) the Didox 007 backing this contract.

    Idempotent on purpose: the partial unique index already forbids a second live
    document per contract, and a user who double-clicks should get the first one
    rather than a 409 they cannot act on.
    """
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.domains.contracts.models import ContractTemplate  # noqa: PLC0415
    from app.domains.contracts.render import render_contract_html  # noqa: PLC0415
    from app.domains.edi import numbering  # noqa: PLC0415
    from app.domains.edi import service as edi_service  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    if contract.signing_provider != "didox":
        raise contract_service.WrongRail(
            f"contract {contract.id} is on the {contract.signing_provider} rail"
        )
    if contract.status != ContractStatus.pending_signatures:
        # Before both sides have accepted, the terms can still change — and a
        # document at the operator cannot be edited, only cancelled.
        raise NotReadyToSend(str(contract.status))

    existing = _existing_document(db, contract)
    if existing is not None:
        return existing

    deal = _linked_deal(db, contract)
    offer = _linked_offer(db, contract, deal)
    seller_id, buyer_id = resolve_parties(contract, deal=deal, offer=offer)
    if acting_company_id != seller_id:
        # The ЭСФ that follows is issued by the seller and quotes this document,
        # so the seller is the one who must own it at the operator.
        raise PartyMismatch(f"company {acting_company_id} is not the seller of contract {contract.id}")

    seller = db.get(Company, seller_id)
    buyer = db.get(Company, buyer_id)
    if seller is None or buyer is None:  # pragma: no cover — FK-guaranteed
        raise PartyMismatch(f"contract {contract.id} references a missing company")

    # Date- and role-sensitive, so read per document and stored with it as
    # evidence of what we asserted on the day. A provider that cannot tell us is
    # not a reason to refuse: Didox accepts the document without it.
    def _vat(tax_id: str, *, is_seller: bool) -> tuple[str | None, int | None]:
        try:
            status_dto = client.vat_reg_status(
                tax_id, document_date=today.isoformat(), is_seller=is_seller, user_key=user_key
            )
        except Exception:  # noqa: BLE001 — their soliq gateway is routinely down
            return None, None
        if status_dto is None:
            return None, None
        return status_dto.code, status_dto.status

    # Only the seller's: the buyer's whole block, VAT code included, comes from
    # the registry lookup, and asking twice invites the two to disagree on the
    # same document.
    seller_vat_code, seller_vat_status = _vat(seller.tax_id, is_seller=True)

    template = db.get(ContractTemplate, contract.template_id)
    if template is None:  # pragma: no cover — FK-guaranteed
        raise EmptyContractBody(f"contract {contract.id} has no template")
    template_html = storage_service.get_object_text(template.body_storage_path)
    initiator = db.get(Company, contract.initiator_company_id)
    counterparty = db.get(Company, contract.counterparty_company_id)
    if initiator is None or counterparty is None:  # pragma: no cover — FK-guaranteed
        raise PartyMismatch(f"contract {contract.id} references a missing company")
    rendered = render_contract_html(
        template_html,
        {**(contract.variables or {}), "title": contract.title},
        contract_service._requisites(db, initiator),  # noqa: SLF001
        contract_service._requisites(db, counterparty),  # noqa: SLF001
        contract_public_id=str(contract.public_id),
        # Empty on purpose: this render exists only to lift the SECTIONS out, and
        # a generation timestamp inside them would be noise in a legal document.
        generated_at="",
    )

    # Allocated ONCE: the ЭСФ quotes it, and the roaming centre refuses a pair
    # whose numbers disagree.
    number = numbering.contract_number(
        deal_number=deal.number if deal is not None else None,
        contract_public_id=str(contract.public_id),
    )
    body = build_body(
        number=number,
        date=today,
        expires_on=today + datetime.timedelta(days=term_days),
        title=contract.title,
        # Two sources, deliberately: we vouch for the seller (they sign here,
        # with a key we watched them use), the tax registry vouches for the buyer
        # (who may not be our user at all, and whose block this document will be
        # checked against). See `party_from_registry`.
        seller=party_from_company(
            db, seller, vat_reg_code=seller_vat_code, vat_reg_status=seller_vat_status
        ),
        buyer=party_from_registry(client, buyer.tax_id),
        lines=lines or suggested_lines(contract, offer),
        sections=sections_from_html(rendered),
    )

    return edi_service.create_document(
        db,
        doc_type="007",
        subject_kind="contract",
        subject_id=int(contract.id),
        owner_company_id=seller_id,
        partner_company_id=buyer_id,
        deal_id=int(deal.id) if deal is not None else None,
        number=number,
        doc_date=today,
        payload=body,
        created_by_user_account_id=account_id,
        user_key=user_key,
        tax_id=seller.tax_id,
        client=client,
    )
