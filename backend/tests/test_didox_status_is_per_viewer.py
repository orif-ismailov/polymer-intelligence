"""Didox's status ladder is RELATIVE, and both parties read the same field.

Two bugs, one root, both visible the moment a real counterparty opened the
screen on 27.08.2026.

`didox_documents.status` holds what Didox answers for `owner=1` — the OWNER's
point of view. `1` means "awaiting partner", so after the seller signs, the
seller correctly sees "waiting for them". The same number was then handed to the
BUYER, whose screen read it the same way and concluded it was waiting for someone
else — so the buyer, whose turn it actually was, got no sign button at all. Their
side of the same document is `2` at Didox (`owner=0`).

The ladder is symmetric: `1` and `2` are one state named from two ends. So the
API answers each viewer in THEIR terms, and one number then drives everything —
whose turn it is, and who has already signed:

    my side signed    ⟺  status ∈ {1, 3}
    their side signed ⟺  status ∈ {2, 3}

Which also fixes the timeline. It was derived from `contract.signatures`, and on
this rail that table stays EMPTY by design — `signature_evidence_id` is NOT NULL
and points at a PKCS#7 we verified, which we never have for a Didox signature.
So «Ожидает подписи: <seller>» was displayed forever, including to the seller who
had just signed.
"""

from __future__ import annotations

import pytest


class TestTheStatusIsTranslatedForTheViewer:
    @pytest.mark.parametrize(
        ("stored", "viewer_is_owner", "expected"),
        [
            (0, True, 0),
            (0, False, 0),
            (1, True, 1),
            (1, False, 2),
            (2, True, 2),
            (2, False, 1),
            (3, True, 3),
            (3, False, 3),
            (4, True, 4),
            (4, False, 4),
            (50, False, 50),
        ],
    )
    def test_only_the_two_turn_taking_states_flip(
        self, stored: int, viewer_is_owner: bool, expected: int
    ) -> None:
        """`1` and `2` are the same state seen from two ends; everything else —
        draft, signed, rejected, annulled — is a fact about the document and
        reads identically from both."""
        from app.domains.contracts.api_portal import _didox_status_for_viewer

        assert _didox_status_for_viewer(stored, viewer_is_owner=viewer_is_owner) == expected

    def test_no_document_is_no_status(self) -> None:
        from app.domains.contracts.api_portal import _didox_status_for_viewer

        assert _didox_status_for_viewer(None, viewer_is_owner=True) is None


class TestTheContractDetailUsesIt:
    def test_the_detail_translates_before_answering(self) -> None:
        import inspect

        from app.domains.contracts import api_portal

        source = inspect.getsource(api_portal._detail_out)  # noqa: SLF001
        assert "_didox_status_for_viewer" in source
        # The raw column must not reach the client — that IS the bug.
        assert "didox_status=didox_doc.status" not in source


class TestTheTimelineStopsReadingAnEmptyTable:
    def test_the_page_derives_didox_steps_from_the_status(self) -> None:
        """On this rail `contract.signatures` is empty by design, so a timeline
        built from it says «ожидает подписи» about a party that has signed."""
        import pathlib

        page = (
            pathlib.Path(__file__).resolve().parents[2]
            / "portal/src/pages/contracts/ContractDetailPage.tsx"
        ).read_text(encoding="utf-8")
        assert "didoxSignedFor" in page

    def test_the_wording_for_a_signature_we_cannot_timestamp(self) -> None:
        """Didox tells us THAT a side signed, never WHEN — so the step may not
        borrow the contract's own «signed at» phrasing and invent a moment."""
        import json
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2] / "portal/src/shared/i18n/locales"
        for lang in ("ru", "uz", "en"):
            data = json.loads((root / f"{lang}.json").read_text(encoding="utf-8"))
            assert "signedNoDate" in data["contracts"]["timeline"], lang
