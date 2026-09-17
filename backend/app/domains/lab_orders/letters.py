"""The sample commitment letter — письмо-обязательство (P7.a — W8).

A buyer asking for a pробная партия commits, in writing and under their own
E-IMZO signature, that **if the material suits them they will contract, and the
sample's price is credited against that contract**. What happens if it does NOT
suit them is written by the seller, per offer — the platform does not invent that
consequence for two other businesses.

Three deliberate choices:

**The document never goes to Didox — but the SIGNER's identity now does, and
that changes what this letter proves.** The undertaking is still commercial, not
fiscal: nothing here reaches soliq, and `purpose='sample_letter'` still marks an
ordinary `SignatureEvidence` row. What is gone is the independent verdict on the
envelope. Verification used to run through the UNICON sidecar, which does not
exist and never ran outside a dev stack; Didox publishes no "verify this PKCS#7"
call, so there is nothing to replace it with.

So the flow now takes TWO signatures from one key session (one password prompt,
via the browser's `openSession`):

  1. over the buyer company's **INN** — Didox authenticates it, which is what
     establishes WHO is signing;
  2. over the **letter hash** — stored verbatim as evidence, and NOT
     cryptographically checked by anything of ours.

The honest reading of the result: we can prove this account, holding a key Didox
accepted for this company, asked us to record a signature over this exact
document at this time. We can no longer prove the envelope itself verifies. The
docstring used to say this flow "has to work before either side has a Didox
account" — that is no longer true, and it is the real cost of the change.

**The seller's terms are SNAPSHOTTED at signing.** `seller_offers.sample_letter_terms`
can be edited at any time; the letter must stay evidence of what was actually
agreed, not of what the seller says today.

**The challenge is derived from the document hash**, exactly like the contract
challenge: `sample_letter:{public_id}:{sha256}`. Any re-render invalidates every
outstanding challenge, so a signature can never attach to a document the signer
did not see.
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.numbering import LOCK_BASE_SAMPLE_LETTER, next_in_sequence
from app.core.time import utcnow
from app.domains.contracts import render as contract_render
from app.domains.contracts.eimzo_models import SignatureEvidence
from app.domains.contracts.models import ContractTemplate
from app.domains.edi.identity import verify_identity
from app.models.enums import SampleRequestStatus
from app.services import audit_service, storage_service

if TYPE_CHECKING:  # pragma: no cover
    import redis
    from sqlalchemy.orm import Session

    from app.domains.accounts.models import UserAccount
    from app.domains.companies.models import Company
    from app.domains.lab_orders.models import SampleRequest

logger = logging.getLogger(__name__)

TEMPLATE_CODE = "SAMPLE_LETTER_V1"
PURPOSE = "sample_letter"

_CHALLENGE_KEY = "eimzo:sample_letter_ch:{sample_id}:{company_id}"


class LetterNotRequired(Exception):
    """This offer does not ask for a commitment letter."""


class LetterAlreadySigned(Exception):
    """Signed once, and a signed letter is immutable."""


class TemplateMissing(Exception):
    """`SAMPLE_LETTER_V1` is not seeded in this deployment."""


class ChallengeExpired(Exception):
    """The challenge is gone, or the document was re-rendered under it."""


class SignatureVerificationFailed(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CertCompanyMismatch(Exception):
    """The certificate belongs to a different company than the one committing."""

    def __init__(self, cert_inn: str, company_inn: str) -> None:
        super().__init__("certificate INN does not match the buyer")
        self.cert_inn_masked = cert_inn
        self.company_inn_masked = company_inn


def next_letter_number(db: Session) -> str:
    """`ПО-{year}-{NNNNNN}` — global per year.

    Unlike an ЭСФ number this is OUR document, not an entry in any seller's tax
    book, so there is nothing to keep per-company.
    """
    year = utcnow().year
    value = next_in_sequence(db, f"sample_letter_seq_{year}", LOCK_BASE_SAMPLE_LETTER + year)
    return f"ПО-{year}-{value:06d}"


#: Party fields a LETTER supplies — a strict subset of the contract set (no bank
#: details). Same role as `contracts.service.REQUISITE_KEYS`: the template validator
#: builds the renderable-name set from it. See that docstring.
REQUISITE_KEYS: frozenset[str] = frozenset({"legal_name", "inn", "address", "director"})


def _requisites(db: Session, company: Company) -> dict[str, object]:
    """Display requisites. No bank account — a commitment letter needs none, and
    the fewer places that decrypt one, the better."""
    return {
        "legal_name": company.legal_name or company.tax_id,
        "inn": company.tax_id,
        "address": company.legal_address or "",
        "director": company.director_name or "",
    }


def render_letter(db: Session, sample: SampleRequest) -> SampleRequest:
    """(Re)render the letter and store it. Idempotent while unsigned.

    Refuses once signed: the PDF is what the signature covers, so re-rendering it
    afterwards would leave a signature attached to bytes nobody agreed to.
    """
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.marketplace.models import SellerOffer  # noqa: PLC0415

    if sample.letter_signed_at is not None:
        raise LetterAlreadySigned(str(sample.id))

    offer = db.get(SellerOffer, sample.offer_id)
    if offer is None or not offer.sample_letter_required:
        raise LetterNotRequired(str(sample.offer_id))

    template = (
        db.query(ContractTemplate)
        .filter(ContractTemplate.code == TEMPLATE_CODE, ContractTemplate.is_active.is_(True))
        .first()
    )
    if template is None:
        raise TemplateMissing(TEMPLATE_CODE)

    buyer = db.get(Company, sample.buyer_company_id)
    seller = db.get(Company, sample.seller_company_id)
    if buyer is None or seller is None:  # pragma: no cover — FK guarantees both
        raise LetterNotRequired(str(sample.id))

    if sample.letter_number is None:
        sample.letter_number = next_letter_number(db)
    # Snapshot the seller's consequence clause NOW, so a later edit to the offer
    # cannot rewrite what the buyer signed up to.
    terms = (offer.sample_letter_terms or "").strip()
    sample.letter_terms_snapshot = terms

    variables: dict[str, object] = {
        "letter_number": sample.letter_number,
        "sample_public_id": str(sample.public_id),
        "product": " ".join(
            part for part in (offer.product_text, offer.grade_text) if part
        )
        or offer.polymer_type
        or "—",
        "sample_qty": sample.qty or "—",
        "sample_price": (
            f"{offer.sample_price} {offer.currency or ''}".strip()
            if offer.sample_price is not None
            else "по договорённости"
        ),
        "delivery_address": sample.delivery_address,
        "offer_id": str(offer.id),
        "seller_terms": terms,
    }
    sample.letter_variables = dict(variables)

    template_html = storage_service.get_object_text(template.body_storage_path)
    pdf = contract_render.render_contract_pdf(
        template_html,
        variables,
        {**_requisites(db, buyer), "_role": "buyer"},
        {**_requisites(db, seller), "_role": "seller"},
        contract_public_id=str(sample.public_id),
        generated_at=utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )
    version_n = int((sample.letter_variables or {}).get("_render_n", 0) or 0) + 1
    path, sha = storage_service.store_sample_letter_pdf(str(sample.public_id), version_n, pdf)
    sample.letter_storage_path = path
    sample.letter_sha256 = sha
    db.flush()
    return sample


def _challenge_value(sample: SampleRequest) -> str:
    """Bound to the document hash — a re-render invalidates outstanding challenges."""
    return f"sample_letter:{sample.public_id}:{sample.letter_sha256}"


def issue_challenge(
    redis_client: redis.Redis[str], sample: SampleRequest, company_id: int
) -> str:
    if sample.letter_signed_at is not None:
        raise LetterAlreadySigned(str(sample.id))
    if not sample.letter_sha256:
        raise ChallengeExpired(str(sample.id))
    challenge = _challenge_value(sample)
    redis_client.setex(
        _CHALLENGE_KEY.format(sample_id=sample.id, company_id=company_id),
        settings.EIMZO_CHALLENGE_TTL_SECONDS,
        challenge,
    )
    return challenge


def sign(
    db: Session,
    redis_client: redis.Redis[str],
    sample: SampleRequest,
    buyer: Company,
    account: UserAccount,
    pkcs7_b64: str,
    *,
    identity_pkcs7: str,
    identity_signature_hex: str,
) -> SampleRequest:
    """Confirm who is signing, store the letter signature, release the request.

    `pkcs7_b64` covers the LETTER hash and is evidence only — see the module
    docstring for why nothing of ours verifies it any more. The `identity_*` pair
    covers the buyer's INN and is what Didox authenticates; both come from one
    key session in the browser, so the person types their password once.

    The state move is the point: until this succeeds the request sits in
    `pending_letter` and the SELLER HAS NOT BEEN TOLD. Signing is what makes it a
    real request.
    """
    if sample.letter_signed_at is not None:
        raise LetterAlreadySigned(str(sample.id))

    key = _CHALLENGE_KEY.format(sample_id=sample.id, company_id=buyer.id)
    challenge = redis_client.getdel(key)
    if not isinstance(challenge, str) or challenge != _challenge_value(sample):
        # Missing, or the letter was re-rendered after the challenge was issued.
        raise ChallengeExpired(str(sample.id))

    # Identity, from the OTHER signature. Didox never sees the letter.
    result = verify_identity(
        redis_client, buyer, pkcs7_64=identity_pkcs7, signature_hex=identity_signature_hex
    )  # ProviderUnavailable propagates
    if not result.ok:
        raise SignatureVerificationFailed(result.error or "signature_invalid")

    cert_inn = result.signer.org_inn if result.signer else None
    if cert_inn and buyer.tax_id and cert_inn != buyer.tax_id:
        from app.domains.contracts.eimzo import _mask_inn  # noqa: PLC0415

        raise CertCompanyMismatch(_mask_inn(cert_inn), _mask_inn(buyer.tax_id))

    try:
        pkcs7_bytes = base64.b64decode(pkcs7_b64)
    except (ValueError, TypeError):
        pkcs7_bytes = pkcs7_b64.encode("utf-8")
    path, sha = storage_service.store_eimzo_pkcs7(buyer.id, pkcs7_bytes)
    signer = result.signer
    evidence = SignatureEvidence(
        company_id=buyer.id,
        user_account_id=account.id,
        purpose=PURPOSE,
        challenge=challenge,
        pkcs7_storage_path=path,
        pkcs7_sha256=sha,
        # Who Didox said was signing — NOT read off this envelope, which nothing
        # parsed. `serial_number` is gone with the sidecar that could read it.
        cert_subject=(
            {
                "org_name": signer.org_name,
                "org_inn": signer.org_inn,
                "position": signer.position,
            }
            if signer
            else None
        ),
        # No provider reports a signing time, so this is ours to stamp, exactly as
        # the contract and identity paths do.
        signed_at=utcnow(),
    )
    db.add(evidence)
    db.flush()

    sample.letter_signature_evidence_id = evidence.id
    sample.letter_signed_at = utcnow()
    if sample.status == SampleRequestStatus.pending_letter:
        sample.status = SampleRequestStatus.requested
    db.flush()

    audit_service.write_audit(
        db, None, "sample.letter_signed", "sample_requests", str(sample.id),
        {"account_id": account.id, "company_id": buyer.id, "letter_number": sample.letter_number},
    )
    return sample
