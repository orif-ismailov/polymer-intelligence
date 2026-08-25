"""Getting a company onto Didox at all (P7.a Stage 2 — W5).

Two steps stand between a verified company and its first document:

  1. **The account must exist.** `POST /v1/auth/signup`, signed with the company's
     own E-IMZO key.
  2. **The public offer must be signed** — once, ever. Until it is, the first SEND
     fails `422 {"context": {"offer": "required"}}` (documented on method 9 of
     "06. Документы"). Nothing before that warns you: reading documents returns
     `200` with an empty list, and creating a draft succeeds.

`GET /v1/profile` DOES report both — it carries `offerSigned` and
`offerDocumentId`. So this state is observable in principle, and
`refresh_from_profile` below uses it when it can. But it cannot be relied on as
the only source: that endpoint answers `422 "Failed to get Phis By Tin Info info
from soliq"` for any company Didox cannot resolve in the tax registry, which on
the test contour is every company whose ЭЦП came from `test.e-imzo.uz` (those
carry synthetic ИНН that soliq has never heard of). So `didox_companies` is the
record, and the profile is a corroborating read when it is available.

This is not a hypothetical failure mode. Didox's OWN registration page performs
exactly these two steps, and on the test contour its second one 500s: both of our
test companies exist with the offer unsigned, which is precisely `OFFER_UNSIGNED`.

**Where this hangs in the product:** a card on the company page, next to the
verification badge — not a step in the registration wizard. The wizard's five steps
are pinned to a mockup, run before verification, and a company registering by hand
may not have an E-IMZO key at that moment; blocking registration on an EDI
operator's public offer would gate the common path on an optional feature. For the
same reason `verification_service.approve()` does not consult any of this.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import TYPE_CHECKING, Protocol

from app.services import settings_service

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

    from app.domains.edi.models import DidoxCompany

logger = logging.getLogger(__name__)

#: Onboarding states, in the order a company passes through them.
NOT_REGISTERED = "not_registered"
OFFER_UNSIGNED = "offer_unsigned"
READY = "ready"
#: Not a state of the company — a state of this DEPLOYMENT.
DISABLED = "disabled"

_MODE_SETTING = "didox_mode"
_MODE_LIVE = "live"


class ChannelDisabled(Exception):
    """This deployment has no Didox document rail (`didox_mode='stub'`).

    Split from an outage on purpose. An operator who never enabled Didox should
    see nothing about it, whereas a configured rail that failed is an event worth
    a line on screen — the same distinction the registry lookup draws.
    """


class _Signer(Protocol):
    """The slice of `DidoxClient` onboarding needs."""

    def timestamp(self, pkcs7_64: str, signature_hex: str) -> str: ...
    def signup(self, signature: str, *, email: str, mobile: str, password: str) -> str: ...
    def offer_base64(self, *, user_key: str | None = ...) -> str: ...
    def create_offer_document(
        self, document_b64: str, *, tax_id: str, user_key: str | None = ...
    ) -> dict[str, object]: ...
    def sign_offer(self, signature: str, *, user_key: str | None = ...) -> object: ...
    def profile(self, *, user_key: str | None = ...) -> dict[str, object]: ...


# ── state ─────────────────────────────────────────────────────────────────────


def state_of(row: DidoxCompany | None) -> str:
    """Read the onboarding state off the record.

    An offer stamp without a signup stamp is still `NOT_REGISTERED`: the two are
    written by different flows, and a send needs both to have happened, so the
    weaker answer is the safe one.
    """
    if row is None or row.signup_at is None:
        return NOT_REGISTERED
    if row.offer_signed_at is None:
        return OFFER_UNSIGNED
    return READY


def channel_state(db: Session) -> str | None:
    """`DISABLED` when this deployment has no document rail, else `None`.

    `None` means "ask `state_of`" — the company's own state is only meaningful once
    the channel exists. Reporting `not_registered` on the stub rail would be a
    claim about a real company's Didox account that nobody ever looked up.
    """
    return None if _is_live(db) else DISABLED


def assert_live(db: Session) -> None:
    """Guard for ACTIONS. Reading a state is harmless; sending is not."""
    if not _is_live(db):
        raise ChannelDisabled(_MODE_SETTING)


def _is_live(db: Session) -> bool:
    return str(settings_service.get(db, _MODE_SETTING)) == _MODE_LIVE


# ── the record ────────────────────────────────────────────────────────────────


def get_or_create(db: Session, company_id: int, tax_id: str) -> DidoxCompany:
    from app.domains.edi.models import DidoxCompany  # noqa: PLC0415

    row = db.get(DidoxCompany, company_id)
    if row is None:
        row = DidoxCompany(company_id=company_id, tin=tax_id)
        db.add(row)
        db.flush()
    return row


def note_signed_in(db: Session, company_id: int, tax_id: str) -> DidoxCompany:
    """A successful `user-key` mint PROVES the account exists.

    That is the only reliable signal we get for step 1 — a company may have
    registered on Didox's own site, in which case we never saw the signup and
    would otherwise keep offering it.
    """
    from app.core.time import utcnow  # noqa: PLC0415

    row = get_or_create(db, company_id, tax_id)
    if row.signup_at is None:
        row.signup_at = utcnow()
        db.flush()
    return row


def note_offer_signed(db: Session, company_id: int, tax_id: str) -> DidoxCompany:
    """Step 2 done — by us, or inferred from a send that Didox accepted."""
    from app.core.time import utcnow  # noqa: PLC0415

    row = get_or_create(db, company_id, tax_id)
    if row.offer_signed_at is None:
        row.offer_signed_at = utcnow()
        db.flush()
    return row


def refresh_from_profile(
    db: Session, company_id: int, tax_id: str, *, client: _Signer, user_key: str
) -> DidoxCompany:
    """Corroborate our record against `GET /v1/profile`, which knows both facts.

    The profile carries `offerSigned` (and `offerDocumentId`), so where it is
    readable it beats anything we inferred. Where it is NOT readable it tells us
    nothing at all — Didox answers `422 "Failed to get Phis By Tin Info info from
    soliq"` for a company it cannot resolve in the tax registry — so a failure here
    leaves our own record untouched rather than downgrading it.

    Never raises: this is a nicety, and onboarding must not depend on it.
    """
    row = get_or_create(db, company_id, tax_id)
    try:
        profile = client.profile(user_key=user_key)
    except Exception as exc:  # noqa: BLE001 — a corroborating read may always fail
        logger.info("didox.profile.unreadable", extra={"tin": tax_id, "error": str(exc)})
        return row
    if not isinstance(profile, dict):
        return row
    # `1`/`0` in every sample we have seen; accept a bool too rather than guess.
    signed = profile.get("offerSigned")
    if signed in (1, True):
        note_offer_signed(db, company_id, tax_id)
    elif signed in (0, False):
        note_offer_required(db, company_id, tax_id)
    return row


def note_offer_required(db: Session, company_id: int, tax_id: str) -> DidoxCompany:
    """A send came back `offer: required` — our record was wrong, so correct it.

    Self-healing in the one direction that matters: we can be wrong about the
    offer being signed (the company might have signed it elsewhere, or Didox might
    have lost it), and the send is where the truth shows up.
    """
    row = get_or_create(db, company_id, tax_id)
    row.offer_signed_at = None
    db.flush()
    return row


# ── the two steps ─────────────────────────────────────────────────────────────


def register(
    db: Session,
    company_id: int,
    tax_id: str,
    *,
    pkcs7_64: str,
    signature_hex: str,
    email: str,
    mobile: str,
    password: str,
    client: _Signer,
) -> str:
    """Create the Didox account and return its first `user-key`.

    NOTE their email validator rejects `+` (verified live), so plus-addressing
    cannot be used to derive one address per company.
    """
    assert_live(db)
    token = client.signup(
        client.timestamp(pkcs7_64, signature_hex),
        email=email,
        mobile=mobile,
        password=password,
    )
    note_signed_in(db, company_id, tax_id)
    return token


def offer_to_sign(db: Session, *, tax_id: str, user_key: str, client: _Signer) -> str:
    """Fetch the public offer, register it as a document, and return WHAT TO SIGN.

    Two round trips, and the ordering is the whole point. The browser cannot know
    the bytes to sign until the document exists, because what gets signed is the
    **JSON `offer/create` returns** — not the PDF that went into it
    (`reference/11-offer-signing.md` step 3: "преобразовать полученный json со 2го
    шага в base64"). Signing the PDF instead produces a signature Didox accepts
    the shape of and then rejects the content of.

    Serialised compactly and without ASCII escaping, matching how every other
    Didox payload is signed — the bytes have to be reproducible, not merely valid.
    """
    assert_live(db)
    pdf_b64 = client.offer_base64(user_key=user_key)
    document_json = client.create_offer_document(pdf_b64, tax_id=tax_id, user_key=user_key)
    payload = json.dumps(document_json, ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def accept_offer(
    db: Session,
    company_id: int,
    tax_id: str,
    *,
    pkcs7_64: str,
    signature_hex: str,
    user_key: str,
    client: _Signer,
) -> None:
    """Sign the prepared offer — the one-time step that unblocks every send."""
    assert_live(db)
    client.sign_offer(client.timestamp(pkcs7_64, signature_hex), user_key=user_key)
    note_offer_signed(db, company_id, tax_id)
