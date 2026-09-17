"""The sample commitment letter (P7.a — W8).

The buyer signs, before the seller is ever told, that **if the material suits them
they will contract and the sample's price is credited against it**. What happens
if it does not suit them is the seller's clause, per offer.

What is asserted here is what would fail quietly:

  * a required letter holds the request in `pending_letter`, and the seller is NOT
    notified — a notification for an unsigned intention has the seller chasing a
    request that may never arrive;
  * the challenge is bound to the letter's sha256, so a re-render invalidates every
    outstanding one and a signature can never attach to bytes the signer did not see;
  * the seller's terms are SNAPSHOTTED, because the offer can be edited afterwards;
  * requiring a letter without writing the terms is refused — defaulting that
    clause would mean inventing a commercial consequence between two other
    companies.
"""

from __future__ import annotations

import uuid

import pytest

from app.domains.lab_orders import letters


class _Sample:
    def __init__(self, *, sha: str | None = "abc123", signed: object = None) -> None:
        self.id = 5
        self.public_id = uuid.UUID("7b520eb7-86a9-420e-8a87-c5c353ea8726")
        self.letter_sha256 = sha
        self.letter_signed_at = signed
        self.letter_number = None


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value

    def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)


class _Account:
    id = 11


class _Buyer:
    id = 3
    tax_id = "301234567"


class _Session:
    """Enough Session for `sign()`: it adds one row and flushes twice.

    `flush` stands in for the DB assigning a PK, which `sign()` reads back into
    `sample.letter_signature_evidence_id`. Hermetic on purpose — the behaviour
    under test is which blob goes where, and that needs no Postgres.
    """

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = 42  # type: ignore[attr-defined]


def _signable():  # noqa: ANN202
    """A sample whose challenge has been issued and whose letter is rendered."""
    sample = _Sample()
    sample.status = __import__(
        "app.models.enums", fromlist=["SampleRequestStatus"]
    ).SampleRequestStatus.pending_letter
    sample.letter_signature_evidence_id = None
    buyer = _Buyer()
    redis_client = _Redis()
    letters.issue_challenge(redis_client, sample, buyer.id)
    return sample, buyer, _Session(), redis_client


# ── the challenge ─────────────────────────────────────────────────────────────


class TestChallenge:
    def test_it_is_bound_to_the_document_hash(self) -> None:
        sample = _Sample(sha="abc123")
        challenge = letters.issue_challenge(_Redis(), sample, 7)

        assert challenge == f"sample_letter:{sample.public_id}:abc123"

    def test_a_re_render_invalidates_an_outstanding_challenge(self) -> None:
        """The whole point of deriving it from the hash: a signature must never
        attach to a document the signer did not see."""
        sample = _Sample(sha="abc123")
        issued = letters.issue_challenge(_Redis(), sample, 7)

        sample.letter_sha256 = "def456"  # re-rendered
        assert letters._challenge_value(sample) != issued

    def test_an_unrendered_letter_has_nothing_to_sign(self) -> None:
        with pytest.raises(letters.ChallengeExpired):
            letters.issue_challenge(_Redis(), _Sample(sha=None), 7)

    def test_a_signed_letter_cannot_be_re_challenged(self) -> None:
        with pytest.raises(letters.LetterAlreadySigned):
            letters.issue_challenge(_Redis(), _Sample(signed=object()), 7)

    def test_the_challenge_is_stored_under_a_per_party_key(self) -> None:
        redis_client = _Redis()
        letters.issue_challenge(redis_client, _Sample(), 7)
        assert "eimzo:sample_letter_ch:5:7" in redis_client.values


# ── numbering ─────────────────────────────────────────────────────────────────


class TestSigningTakesTwoSignaturesForTwoDifferentJobs:
    """`sign()` had NO test before this — the challenge lifecycle was covered and
    the signing path was not, which is how it could change rails unnoticed.

    Since verification moved off the UNICON sidecar, two envelopes arrive: one
    over the buyer's INN that Didox authenticates, and one over the letter hash
    that we store and nobody checks. Everything here guards the one mistake that
    would be both catastrophic and invisible — putting them the wrong way round,
    which would file the INN signature as the signed letter and hand the letter
    blob to Didox as proof of identity.
    """

    @staticmethod
    def _run(monkeypatch, *, ok=True, org_inn="301234567"):  # noqa: ANN001, ANN205
        from app.domains.edi.identity import DidoxIdentityResult, DidoxSigner
        from app.domains.lab_orders import letters
        from app.services import audit_service, storage_service

        seen: dict[str, object] = {}

        def fake_verify_identity(redis_client, company, *, pkcs7_64, signature_hex, client=None):  # noqa: ANN001, ANN202, ARG001
            seen["identity_blob"] = pkcs7_64
            seen["identity_hex"] = signature_hex
            return DidoxIdentityResult(
                ok=ok,
                signer=DidoxSigner(org_inn=org_inn, full_name="IVANOV IVAN") if ok else None,
                error=None if ok else "signature_invalid",
            )

        def fake_store(company_id, blob):  # noqa: ANN001, ANN202, ARG001
            seen["stored_blob"] = blob
            return ("evidence/x.p7s", "sha-of-stored")

        monkeypatch.setattr(letters, "verify_identity", fake_verify_identity)
        monkeypatch.setattr(storage_service, "store_eimzo_pkcs7", fake_store)
        monkeypatch.setattr(audit_service, "write_audit", lambda *a, **k: None)
        return letters, seen

    def _sign(self, letters, sample, buyer, db, redis_client):  # noqa: ANN001, ANN202
        import base64

        return letters.sign(
            db, redis_client, sample, buyer, _Account(),
            base64.b64encode(b"LETTER-SIGNATURE").decode(),
            identity_pkcs7=base64.b64encode(b"INN-SIGNATURE").decode(),
            identity_signature_hex="ab" * 64,
        )

    def test_the_letter_blob_is_stored_and_the_inn_blob_is_verified(self, monkeypatch) -> None:  # noqa: ANN001
        letters, seen = self._run(monkeypatch)
        sample, buyer, db, redis_client = _signable()

        self._sign(letters, sample, buyer, db, redis_client)

        assert seen["stored_blob"] == b"LETTER-SIGNATURE", (
            "evidence must hold the signature over the DOCUMENT, not over the INN"
        )
        import base64
        assert seen["identity_blob"] == base64.b64encode(b"INN-SIGNATURE").decode(), (
            "Didox authenticates the INN signature — the letter never goes to them"
        )
        assert seen["identity_hex"] == "ab" * 64

    def test_signing_releases_the_request_to_the_seller(self, monkeypatch) -> None:  # noqa: ANN001
        from app.models.enums import SampleRequestStatus

        letters, _ = self._run(monkeypatch)
        sample, buyer, db, redis_client = _signable()

        self._sign(letters, sample, buyer, db, redis_client)

        assert sample.letter_signed_at is not None
        assert sample.status == SampleRequestStatus.requested

    def test_an_identity_didox_refuses_does_not_sign_the_letter(self, monkeypatch) -> None:  # noqa: ANN001
        letters, _ = self._run(monkeypatch, ok=False)
        sample, buyer, db, redis_client = _signable()

        with pytest.raises(letters.SignatureVerificationFailed):
            self._sign(letters, sample, buyer, db, redis_client)
        assert sample.letter_signed_at is None

    def test_a_key_belonging_to_another_company_is_refused(self, monkeypatch) -> None:  # noqa: ANN001
        letters, _ = self._run(monkeypatch, org_inn="999999999")
        sample, buyer, db, redis_client = _signable()

        with pytest.raises(letters.CertCompanyMismatch):
            self._sign(letters, sample, buyer, db, redis_client)
        assert sample.letter_signed_at is None


def test_letter_numbers_are_global_per_year(monkeypatch) -> None:  # noqa: ANN001
    """OUR document, not an entry in any seller's tax book — so unlike an ЭСФ
    there is nothing to keep per company."""
    seen: dict[str, object] = {}

    def _next(db: object, sequence: str, lock_key: int) -> int:
        seen["sequence"] = sequence
        seen["lock_key"] = lock_key
        return 42

    monkeypatch.setattr(letters, "next_in_sequence", _next)
    number = letters.next_letter_number(object())

    assert number.startswith("ПО-")
    assert number.endswith("-000042")
    assert str(seen["sequence"]).startswith("sample_letter_seq_")
    assert "_" not in str(seen["sequence"]).removeprefix("sample_letter_seq_")


# ── the request gate ──────────────────────────────────────────────────────────


def test_a_letter_offer_holds_the_request_before_the_seller_sees_it() -> None:
    """`pending_letter` is not a draft — it is "asked, but not yet undertaken"."""
    from app.domains.lab_orders import samples
    from app.models.enums import SampleRequestStatus

    assert samples._TRANSITIONS[SampleRequestStatus.pending_letter] == {
        SampleRequestStatus.requested
    }
    # And it is NOT a party decision, so no actor may drive it by hand.
    assert samples.actor_for(SampleRequestStatus.requested) is None


def test_pending_letter_holds_the_offer_buyer_slot() -> None:
    """Otherwise a buyer could open unlimited unsigned drafts against one offer."""
    from app.domains.lab_orders.models import SampleRequest

    index = next(
        ix for ix in SampleRequest.__table__.indexes if ix.name == "uq_sample_request_active"
    )
    predicate = str(index.dialect_options["postgresql"]["where"])
    assert "pending_letter" in predicate


# ── the seller's terms ────────────────────────────────────────────────────────


class TestSellerTerms:
    def test_requiring_a_letter_without_terms_is_refused(self) -> None:
        """Defaulting the clause would mean the platform inventing a commercial
        consequence between two other businesses; an empty one would put a blank
        section into a document the buyer signs."""
        from pydantic import ValidationError

        from app.domains.companies.schemas import CompanyOfferIn

        with pytest.raises(ValidationError):
            CompanyOfferIn(sample_letter_required=True, sample_letter_terms="   ")

    def test_a_letter_with_terms_is_accepted(self) -> None:
        from app.domains.companies.schemas import CompanyOfferIn

        offer = CompanyOfferIn(
            sample_letter_required=True,
            sample_letter_terms="Если материал не подойдёт — покупатель оплачивает пробу и доставку.",
        )
        assert offer.sample_letter_required is True

    def test_not_requiring_a_letter_needs_no_terms(self) -> None:
        from app.domains.companies.schemas import CompanyOfferIn

        assert CompanyOfferIn().sample_letter_required is False


# ── evidence ──────────────────────────────────────────────────────────────────


def test_the_letter_purpose_is_distinct_from_a_contract_signature() -> None:
    """`signature_evidence.purpose` is plain text, so this needed no enum
    migration — but it must still be its OWN value: a commitment letter is not a
    contract, and evidence that conflates them cannot be audited apart."""
    from app.domains.contracts.service import _PURPOSE_CONTRACT

    assert letters.PURPOSE == "sample_letter"
    assert letters.PURPOSE != _PURPOSE_CONTRACT


def test_the_letter_template_is_seeded_as_its_own_kind() -> None:
    """It shares `contract_templates` with contracts; `kind` is what keeps the
    contract picker from offering a letter as something to sign."""
    from app.seed.seed_contract_templates import _SAMPLE_LETTER_V1_SCHEMA

    assert letters.TEMPLATE_CODE == "SAMPLE_LETTER_V1"
    assert "seller_terms" in _SAMPLE_LETTER_V1_SCHEMA["required"]  # type: ignore[operator]


def test_the_three_letter_routes_are_mounted() -> None:
    from app.main import create_app

    paths = set(create_app().openapi()["paths"])
    assert "/api/v1/portal/samples/{sample_id}/letter" in paths
    assert "/api/v1/portal/samples/{sample_id}/letter/challenge" in paths
    assert "/api/v1/portal/samples/{sample_id}/letter/sign" in paths


# ── what the CLIENT needs to show it (W8 portal half) ─────────────────────────


class TestLetterIsReachableFromTheClient:
    """The letter existed only inside the API: rendered, challengeable, signable —
    and invisible. Nothing in the list said a letter was owed, and the PDF had no
    route out, so a buyer could not read what they were about to sign.
    """

    def test_the_list_row_says_whether_a_letter_is_owed(self) -> None:
        from app.domains.lab_orders.schemas import SampleRequestOut

        fields = set(SampleRequestOut.model_fields)
        assert {"letter_required", "letter_signed_at", "letter_number"} <= fields

    def test_the_pdf_has_a_route(self) -> None:
        from app.main import create_app

        paths = set(create_app().openapi()["paths"])
        assert "/api/v1/portal/samples/{sample_id}/letter/document" in paths
