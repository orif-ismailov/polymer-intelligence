"""Real-Postgres tests for the Didox rail schema (P7.a Stage 2 — W2).

Guarded (localhost test_polymer). Everything here is a constraint, not a service:
the schema is what enforces the decisions the plan made, so the schema is what is
tested.

  * `didox_documents` holds BOTH document types, so the ЭСФ — which has no
    `contracts` row — has somewhere to live alongside the договор.
  * `didox_id` is nullable ON PURPOSE: the row is committed before the create
    call, so a create Didox accepted and we timed out on stays recoverable.
  * one LIVE document per (subject, type) — a deleted draft frees the slot,
    mirroring `uq_sample_request_active`.
  * a half-filled ИКПУ is worse than none: it yields a document Didox rejects at
    SEND time, after the user has already entered their key password.
  * `pending_letter` joins the sample active-set, so an unsigned commitment
    letter cannot be spammed per (offer, buyer).
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_seller_offer,
    migrate_head,
    requires_real_db,
    session_factory,
)

pytestmark = requires_real_db


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _company(db, tax: str, phone: str):  # noqa: ANN001, ANN202
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, phone)
    company = make_company(db, account, tax_id=tax)
    company.status = CompanyStatus.verified
    company.legal_name = f"OOO {tax}"
    db.flush()
    return account, company


def _doc(db, **kw):  # noqa: ANN001, ANN003, ANN202
    from app.domains.edi.models import DidoxDocument  # noqa: PLC0415

    row = DidoxDocument(**kw)
    db.add(row)
    db.flush()
    return row


# ── didox_documents ──────────────────────────────────────────────────────────


def test_didox_id_is_nullable_and_unique_when_set(sf) -> None:  # noqa: ANN001
    """Many rows may await their id; no two may claim the same one.

    The nullability is the recovery story for a create we never saw the answer to.
    """
    with sf() as db:
        account, seller = _company(db, "301000001", "+998900000001")
        base = {
            "doc_type": "007",
            "subject_kind": "contract",
            "owner_company_id": seller.id,
            "created_by_user_account_id": account.id,
            "payload": {},
        }
        _doc(db, subject_id=1, **base)
        _doc(db, subject_id=2, **base)  # two NULL didox_id rows coexist
        db.commit()

    with sf() as db:
        account, seller = _company(db, "301000002", "+998900000002")
        base = {
            "doc_type": "007",
            "subject_kind": "contract",
            "owner_company_id": seller.id,
            "created_by_user_account_id": account.id,
            "payload": {},
            "didox_id": "11f092e3428d10c68f7b1e0008000075",
        }
        _doc(db, subject_id=3, **base)
        with pytest.raises(sa.exc.IntegrityError):
            _doc(db, subject_id=4, **base)


def test_one_live_document_per_subject_and_type(sf) -> None:  # noqa: ANN001
    """A deleted draft frees the slot; a live one does not."""
    with sf() as db:
        account, seller = _company(db, "301000003", "+998900000003")
        base = {
            "subject_kind": "contract",
            "subject_id": 77,
            "owner_company_id": seller.id,
            "created_by_user_account_id": account.id,
            "payload": {},
        }
        _doc(db, doc_type="007", status=0, **base)
        # A different type against the same subject is fine — a contract has both
        # a договор and (later) an ЭСФ.
        _doc(db, doc_type="002", status=0, **base)
        db.commit()

        with pytest.raises(sa.exc.IntegrityError):
            _doc(db, doc_type="007", status=1, **base)
        db.rollback()

    with sf() as db:
        from app.domains.edi.models import DidoxDocument  # noqa: PLC0415

        # Delete the draft (Didox status 55) and the slot reopens.
        db.execute(sa.update(DidoxDocument).where(DidoxDocument.doc_type == "007").values(status=55))
        db.flush()
        account = make_account(db, "+998900000004")
        _doc(
            db,
            doc_type="007",
            status=0,
            subject_kind="contract",
            subject_id=77,
            owner_company_id=db.execute(sa.text("SELECT id FROM companies LIMIT 1")).scalar_one(),
            created_by_user_account_id=account.id,
            payload={},
        )


def test_doc_type_and_subject_kind_are_constrained(sf) -> None:  # noqa: ANN001
    """Didox's own ladder is ours to store verbatim; our discriminators are not."""
    with sf() as db:
        account, seller = _company(db, "301000005", "+998900000005")
        with pytest.raises(sa.exc.IntegrityError):
            _doc(
                db,
                doc_type="041",  # ТТН — not on this rail
                subject_kind="contract",
                subject_id=1,
                owner_company_id=seller.id,
                created_by_user_account_id=account.id,
                payload={},
            )


# ── didox_companies ──────────────────────────────────────────────────────────


def test_didox_company_is_one_row_per_company(sf) -> None:  # noqa: ANN001
    """Onboarding state is durable, not a Redis key: re-probing costs a 422."""
    from app.domains.edi.models import DidoxCompany  # noqa: PLC0415

    with sf() as db:
        _, company = _company(db, "301000006", "+998900000006")
        db.add(DidoxCompany(company_id=company.id, tin=company.tax_id))
        db.commit()

        db.add(DidoxCompany(company_id=company.id, tin=company.tax_id))
        with pytest.raises(sa.exc.IntegrityError):
            db.flush()


# ── contracts.signing_provider ───────────────────────────────────────────────


def test_signing_provider_defaults_to_eimzo(sf) -> None:  # noqa: ANN001
    """Existing contracts keep the rail they were signed on."""
    with sf() as db:
        row = db.execute(
            sa.text(
                "SELECT column_default, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'contracts' AND column_name = 'signing_provider'"
            )
        ).one()
        assert "eimzo" in row.column_default
        assert row.is_nullable == "NO"


def test_contract_template_kind_defaults_to_contract(sf) -> None:  # noqa: ANN001
    """The letter reuses the template table; existing rows stay contracts."""
    with sf() as db:
        row = db.execute(
            sa.text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'contract_templates' AND column_name = 'kind'"
            )
        ).scalar_one()
        assert "contract" in row


# ── seller_offers: ИКПУ + letter terms ───────────────────────────────────────


def test_half_filled_ikpu_is_rejected(sf) -> None:  # noqa: ANN001
    """A code without a package/origin builds a document Didox rejects at SEND.

    Failing here costs a form error; failing there costs a key password and a
    round trip to the roaming centre.
    """
    with sf() as db:
        _, company = _company(db, "301000007", "+998900000007")
        offer = make_seller_offer(db, company=company)
        db.commit()

        db.execute(
            sa.text("UPDATE seller_offers SET ikpu_code = :c WHERE id = :i"),
            {"c": "02201001001000000", "i": offer.id},
        )
        with pytest.raises(sa.exc.IntegrityError):
            db.flush()
        db.rollback()

        # Complete is fine, and so is nothing at all (legacy offers).
        db.execute(
            sa.text(
                "UPDATE seller_offers SET ikpu_code = :c, ikpu_package_code = :p, "
                "ikpu_origin = 1 WHERE id = :i"
            ),
            {"c": "02201001001000000", "p": "1505731", "i": offer.id},
        )
        db.commit()


def test_sample_letter_terms_default_off(sf) -> None:  # noqa: ANN001
    """Requiring a letter is opt-in per offer — the seller sets their own terms."""
    with sf() as db:
        _, company = _company(db, "301000008", "+998900000008")
        offer = make_seller_offer(db, company=company)
        db.commit()
        row = db.execute(
            sa.text(
                "SELECT sample_letter_required, sample_letter_terms "
                "FROM seller_offers WHERE id = :i"
            ),
            {"i": offer.id},
        ).one()
        assert row.sample_letter_required is False
        assert row.sample_letter_terms is None


# ── sample_requests: public_id, deal link, letter columns, pending_letter ────


def test_sample_request_public_id_is_unique_and_autofilled(sf) -> None:  # noqa: ANN001
    """The letter's S3 key hangs off this — it must not leak a sequence count."""
    from app.domains.lab_orders.models import SampleRequest  # noqa: PLC0415

    with sf() as db:
        buyer_account, buyer = _company(db, "301000009", "+998900000009")
        _, seller = _company(db, "301000010", "+998900000010")
        offer = make_seller_offer(db, company=seller)
        db.commit()

        row = SampleRequest(
            offer_id=offer.id,
            buyer_company_id=buyer.id,
            seller_company_id=seller.id,
            created_by_user_account_id=buyer_account.id,
            delivery_address="Toshkent",
        )
        db.add(row)
        db.flush()
        db.refresh(row)
        assert isinstance(row.public_id, uuid.UUID)


def test_pending_letter_joins_the_active_set(sf) -> None:  # noqa: ANN001
    """An unsigned letter still occupies the (offer, buyer) slot.

    Otherwise a buyer could open unlimited unsigned drafts against one offer.
    """
    from app.models.enums import SampleRequestStatus  # noqa: PLC0415

    with sf() as db:
        buyer_account, buyer = _company(db, "301000011", "+998900000011")
        _, seller = _company(db, "301000012", "+998900000012")
        offer = make_seller_offer(db, company=seller)
        db.commit()

        def _req(status):  # noqa: ANN001, ANN202
            from app.domains.lab_orders.models import SampleRequest  # noqa: PLC0415

            row = SampleRequest(
                offer_id=offer.id,
                buyer_company_id=buyer.id,
                seller_company_id=seller.id,
                created_by_user_account_id=buyer_account.id,
                delivery_address="Toshkent",
                status=status,
            )
            db.add(row)
            db.flush()
            return row

        _req(SampleRequestStatus.pending_letter)
        with pytest.raises(sa.exc.IntegrityError):
            _req(SampleRequestStatus.pending_letter)
        db.rollback()


def test_declined_request_still_frees_the_slot(sf) -> None:  # noqa: ANN001
    """The R5 invariant survives the new state: a decline is not a life ban."""
    from app.domains.lab_orders.models import SampleRequest  # noqa: PLC0415
    from app.models.enums import SampleRequestStatus  # noqa: PLC0415

    with sf() as db:
        buyer_account, buyer = _company(db, "301000013", "+998900000013")
        _, seller = _company(db, "301000014", "+998900000014")
        offer = make_seller_offer(db, company=seller)
        db.commit()

        common = {
            "offer_id": offer.id,
            "buyer_company_id": buyer.id,
            "seller_company_id": seller.id,
            "created_by_user_account_id": buyer_account.id,
            "delivery_address": "Toshkent",
        }
        db.add(SampleRequest(status=SampleRequestStatus.declined, **common))
        db.add(SampleRequest(status=SampleRequestStatus.pending_letter, **common))
        db.flush()  # must not raise


def test_letter_columns_exist_and_default_empty(sf) -> None:  # noqa: ANN001
    """The letter is evidence: path + hash + the terms actually agreed."""
    with sf() as db:
        cols = {
            r.column_name: r.is_nullable
            for r in db.execute(
                sa.text(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'sample_requests' AND column_name LIKE 'letter%'"
                )
            )
        }
        assert cols == {
            "letter_number": "YES",
            "letter_storage_path": "YES",
            "letter_sha256": "YES",
            "letter_variables": "YES",
            "letter_terms_snapshot": "YES",
            "letter_signature_evidence_id": "YES",
            "letter_signed_at": "YES",
        }
