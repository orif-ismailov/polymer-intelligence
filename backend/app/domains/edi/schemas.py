"""Portal DTOs for the Didox rail (P7.a Stage 2 — W5)."""

from __future__ import annotations

import datetime
import decimal

from pydantic import BaseModel, Field

from app.domains.edi.payloads import JsonObject


class DidoxStatusOut(BaseModel):
    """Where a company stands with Didox.

    `state` is one of `disabled` · `not_registered` · `offer_unsigned` · `ready`.
    `disabled` is a property of the DEPLOYMENT, not of the company: on it the
    portal renders nothing at all, because announcing a feature nobody enabled is
    noise, and reporting a company state we never checked would be worse.
    """

    state: str
    #: True when a live `user-key` is cached. The card shows "sign in to Didox"
    #: rather than failing an action later — but its absence never blocks the UI,
    #: since every action mints on demand and then continues.
    has_session: bool = False
    #: Whether THIS account may register the company at Didox and accept its
    #: offer — the owner only. Everyone else sees the state and nothing to press.
    can_onboard: bool = False


class DidoxSignatureIn(BaseModel):
    """A browser signature, both halves.

    `signature_hex` is not optional: `/v1/dsvs/timestamp` requires it, and every
    Didox `signature` field wants the TSA token rather than the bare PKCS#7.
    """

    pkcs7_64: str = Field(min_length=1)
    signature_hex: str = Field(min_length=1)


class DidoxSignupIn(DidoxSignatureIn):
    """Registration details for a company that has no Didox account yet.

    Didox's validator REJECTS `+` in an email — verified on the live contour — so
    plus-addressing cannot be used to derive one address per company.
    """

    email: str = Field(min_length=3, max_length=255)
    mobile: str = Field(min_length=9, max_length=20)
    password: str = Field(min_length=8, max_length=128)


class DidoxOfferOut(BaseModel):
    """The bytes to sign, base64 — signed once per company, ever.

    NOT the offer PDF: the signature must cover the JSON that `offer/create`
    returns, so this endpoint performs that create and hands back its result.
    Signing the PDF yields a well-formed signature over the wrong content.
    """

    document_b64: str


class DidoxOfferIn(DidoxSignatureIn):
    """The signed offer — signature only; the document already exists on their side."""


class DidoxSessionOut(BaseModel):
    """Minting succeeded. The key itself never leaves the server."""

    state: str
    has_session: bool = True


class DidoxSignPayloadOut(BaseModel):
    """Round 1 of signing: the exact bytes, and which flow they belong to.

    `mode` is `outgoing` (we own the document — sign its stored JSON) or
    `incoming` (the counterparty sent it — sign its base64, then the server joins
    our signature with theirs). The browser does not have to work that out.
    """

    data_b64: str
    mode: str


class DidoxDocumentOut(BaseModel):
    """A document after a send."""

    id: int
    doc_type: str
    number: str | None
    #: Didox's own status ladder, verbatim: 0 draft · 1 awaiting partner ·
    #: 2 awaiting us · 3 signed · 4 rejected · 50 annulled by the tax committee.
    status: int
    didox_id: str | None
    #: True when this signature completed the contract on the Didox rail.
    activated: bool = False
    archive_sha256: str | None = None
    #: Non-null means the tax committee accepted WITH remarks — a success with a
    #: note, not a failure.
    warning: JsonObject | None = None


class DidoxContractLineIn(BaseModel):
    """One product line the seller confirms before the document exists.

    Confirmed rather than derived: the tax classification of the goods is what
    reaches my.soliq.uz, and «мы так поняли из объявления» is not a defence. The
    prefill fills these in; the seller can correct them.
    """

    name: str = Field(min_length=1, max_length=500)
    count: decimal.Decimal = Field(gt=0)
    price: decimal.Decimal = Field(ge=0)
    #: `None` means supplied WITHOUT VAT — a different statement from a 0% rate.
    vat_rate: int | None = Field(default=12, ge=0, le=100)


class DidoxIkpuIn(BaseModel):
    """The seller's ИКПУ for a contract with no offer to take it from (a tender).

    Complete or refused: the code, its package and the seller's `origin` all reach
    my.soliq.uz, and `ck_offer_ikpu_complete` asks the same of an offer.
    """

    #: 17 digits — the tasnif.soliq.uz format.
    code: str = Field(pattern=r"^\d{17}$")
    name: str = Field(min_length=1, max_length=500)
    package_code: str = Field(min_length=1, max_length=50)
    package_name: str = Field(default="", max_length=200)
    #: How THIS seller came by the goods — Didox never supplies it.
    origin: int = Field(ge=1, le=4)


class DidoxContractDocumentIn(BaseModel):
    lines: list[DidoxContractLineIn] = Field(default_factory=list)
    #: Only for a contract without an offer; an offer's own code always wins.
    ikpu: DidoxIkpuIn | None = None


class DidoxContractPrefillOut(BaseModel):
    """What the seller is about to send, and what stops them if anything does."""

    contract_id: int
    seller_company_id: int
    buyer_company_id: int
    seller_name: str | None = None
    buyer_name: str | None = None
    #: Already created — the screen shows the document instead of the form.
    document_id: int | None = None
    lines: list[DidoxContractLineIn] = Field(default_factory=list)
    #: No offer behind this contract (it came from a tender), so the seller picks
    #: the ИКПУ on the card instead of it arriving from the listing.
    ikpu_choice: bool = False
    #: Machine-readable reasons the create would fail, so the UI can fix each in
    #: place: `ikpu_missing` · `signer_identity_missing` · `not_ready` ·
    #: `wrong_rail` · `not_seller` · `counterparty_unknown` (the buyer's ИНН is
    #: not in the operator's registry) · `counterparty_ikpu_missing` (they have
    #: not declared this ИКПУ in their own Didox account). The last two are the
    #: refusals that otherwise arrive only after the seller has signed, and
    #: neither can be fixed from this side — only shown.
    blockers: list[str] = Field(
        default_factory=list,
        description=(
            "ikpu_missing · signer_identity_missing · not_ready · wrong_rail · "
            "not_seller · counterparty_unknown · counterparty_ikpu_missing"
        ),
    )


class DidoxFactureLineOut(BaseModel):
    """A line the invoice form starts from.

    `count` is what is left to invoice; `price` is None when the contract is not
    priced in soum — an ЭСФ is, and the seller must state the soum price.
    """

    ord_no: int
    name: str
    count: decimal.Decimal | None
    price: decimal.Decimal | None
    vat_rate: int | None
    unit: str | None


class DidoxFactureOut(BaseModel):
    """One invoice of a contract, with its status as the READER sees it."""

    id: int
    number: str | None
    doc_date: datetime.date | None
    status: int
    #: True when the reader's company issued it (the seller).
    outgoing: bool
    #: Sum of the lines including VAT.
    total: decimal.Decimal
    #: The specification it invoices, on a framework contract.
    specification_id: int | None = None


class DidoxFacturesOut(BaseModel):
    """The contract's invoices, and what the seller would issue next."""

    contract_id: int
    currency: str | None
    is_seller: bool
    #: No ИКПУ to take from an offer or the signed 007 — the form asks for one.
    ikpu_choice: bool = False
    lines: list[DidoxFactureLineOut] = Field(default_factory=list)
    documents: list[DidoxFactureOut] = Field(default_factory=list)
    #: An unsigned draft — sign it before issuing another.
    pending_document_id: int | None = None
    blockers: list[str] = Field(
        default_factory=list,
        description=(
            "not_active · not_seller · signer_identity_missing · "
            "contract_reference_missing · counterparty_unknown · specification_required"
        ),
    )


class DidoxFactureIn(BaseModel):
    lines: list[DidoxContractLineIn] = Field(min_length=1, max_length=50)
    #: Required on a framework contract: the SIGNED specification this invoices.
    specification_id: int | None = None
    #: Only when `ikpu_choice` was true — otherwise the known code wins.
    ikpu: DidoxIkpuIn | None = None


class DidoxAdminDocumentOut(BaseModel):
    """One Didox document, as staff need to read it."""

    id: int
    doc_type: str
    number: str | None
    #: Didox's ladder verbatim — 4 and 50 are the two that need a person.
    status: int
    didox_id: str | None
    subject_kind: str
    subject_id: int
    deal_id: int | None
    owner_company_id: int
    #: True once the evidence archive has been fetched and hashed.
    archived: bool
    status_synced_at: datetime.datetime | None
    last_error: str | None


class DidoxAdminCompanyOut(BaseModel):
    """Where a company stands with Didox onboarding."""

    company_id: int
    tin: str
    state: str
    signup_at: datetime.datetime | None
    offer_signed_at: datetime.datetime | None
    last_polled_at: datetime.datetime | None
    last_error: str | None
