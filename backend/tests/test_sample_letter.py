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
