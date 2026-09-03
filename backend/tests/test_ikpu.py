"""ИКПУ on the offer (P7.a Stage 2 — W9).

The tax classification of the goods is chosen ONCE by the seller, on their own
offer, and reused by every договор and ЭСФ it backs. Everything asserted here is a
way that could go wrong silently:

  * a HALF-filled code builds a document Didox rejects at SEND time — after the
    seller has loaded a key and typed its password — so it fails in the form;
  * an offer with NO code cannot back a document at all, and that raises rather
    than defaulting: inventing a tax classification for someone else's goods is
    not ours to do;
  * their gateway being unreachable is an OUTAGE, not an empty result. An empty
    list reads as "no such code exists", and a seller would work around it by
    typing something plausible.
"""

from __future__ import annotations

import decimal

import pytest

D = decimal.Decimal


class _Offer:
    def __init__(self, **kw: object) -> None:
        self.id = 91
        self.ikpu_code = kw.get("ikpu_code")
        self.ikpu_name = kw.get("ikpu_name")
        self.ikpu_package_code = kw.get("ikpu_package_code")
        self.ikpu_package_name = kw.get("ikpu_package_name")
        self.ikpu_origin = kw.get("ikpu_origin")


COMPLETE = {
    "ikpu_code": "02201001001000000",
    "ikpu_name": "Полиэтилен линейный",
    "ikpu_package_code": "1505731",
    "ikpu_package_name": "кг",
    "ikpu_origin": 1,
}


# ── the all-or-nothing rule ───────────────────────────────────────────────────


class TestOfferValidation:
    def test_a_code_without_a_package_is_refused(self) -> None:
        from pydantic import ValidationError

        from app.domains.companies.schemas import CompanyOfferIn

        with pytest.raises(ValidationError):
            CompanyOfferIn(ikpu_code="02201001001000000", ikpu_origin=1)

    def test_a_code_without_an_origin_is_refused(self) -> None:
        """`Origin` ends up on every ЭСФ line and is not ours to guess."""
        from pydantic import ValidationError

        from app.domains.companies.schemas import CompanyOfferIn

        with pytest.raises(ValidationError):
            CompanyOfferIn(ikpu_code="02201001001000000", ikpu_package_code="1505731")

    def test_a_complete_code_is_accepted(self) -> None:
        from app.domains.companies.schemas import CompanyOfferIn

        offer = CompanyOfferIn(**COMPLETE)  # type: ignore[arg-type]
        assert offer.ikpu_code == "02201001001000000"

    def test_no_code_at_all_is_a_legitimate_offer(self) -> None:
        """Legacy offers are NOT back-filled, and never will be."""
        from app.domains.companies.schemas import CompanyOfferIn

        assert CompanyOfferIn().ikpu_code is None

    def test_origin_is_bounded_to_the_four_real_values(self) -> None:
        from pydantic import ValidationError

        from app.domains.companies.schemas import CompanyOfferIn

        with pytest.raises(ValidationError):
            CompanyOfferIn(**{**COMPLETE, "ikpu_origin": 9})  # type: ignore[arg-type]


# ── the one door onto a document line ─────────────────────────────────────────


class TestLineFromOffer:
    def test_a_complete_offer_produces_a_line(self) -> None:
        from app.domains.edi.payloads import line_from_offer

        line = line_from_offer(
            _Offer(**COMPLETE), ord_no=1, name="Полиэтилен LL 0209AA",
            count=D("1000"), price=D("14553.57"),
        )
        assert line.catalog_code == "02201001001000000"
        assert line.package_code == "1505731"
        assert line.origin == 1

    def test_an_offer_without_a_code_cannot_back_a_document(self) -> None:
        from app.domains.edi.payloads import IkpuMissing, line_from_offer

        with pytest.raises(IkpuMissing) as exc:
            line_from_offer(_Offer(), ord_no=1, name="x", count=D("1"), price=D("1"))
        assert exc.value.offer_id == 91

    def test_a_half_filled_offer_is_caught_here_too(self) -> None:
        """Belt and braces: the schema and the DB CHECK both refuse it, but this is
        the last gate before a payload is built."""
        from app.domains.edi.payloads import IkpuMissing, line_from_offer

        with pytest.raises(IkpuMissing):
            line_from_offer(
                _Offer(ikpu_code="02201001001000000"), ord_no=1, name="x",
                count=D("1"), price=D("1"),
            )

    def test_the_name_falls_back_to_the_code(self) -> None:
        """A document must carry a `CatalogName`; the code is a truthful stand-in
        where Didox gave us no label."""
        from app.domains.edi.payloads import line_from_offer

        offer = _Offer(**{**COMPLETE, "ikpu_name": None})
        line = line_from_offer(offer, ord_no=1, name="x", count=D("1"), price=D("1"))
        assert line.catalog_name == "02201001001000000"


# ── the upstream outage ───────────────────────────────────────────────────────


class TestUpstreamOutage:
    def test_their_gateway_failure_is_an_outage_not_an_empty_result(self) -> None:
        """Recorded live: `422 {"success": false, "error": "cURL error 6: Could not
        resolve host: gnk-gw.didox77.uz …"}`. Returning `[]` would read as "no such
        code exists" and the seller would type one in."""
        from app.domains.marketplace.api_portal_ikpu import _provider_error
        from app.integrations.didox import DidoxError

        exc = _provider_error(
            DidoxError(422, "cURL error 6: Could not resolve host: gnk-gw.didox77.uz")
        )
        assert exc.status_code == 503
        assert exc.detail == "didox_ikpu_unavailable"

    def test_their_second_outage_shape_is_also_an_outage(self) -> None:
        """Recorded live hours after the cURL one, from the same endpoint:
        `Failed to get class codes by tin`. It carries NO hint that it is upstream
        — it reads like a rejection of our search — so a seller would be told
        their query was wrong when their query was fine."""
        from app.domains.marketplace.api_portal_ikpu import _provider_error
        from app.integrations.didox import DidoxError

        exc = _provider_error(DidoxError(422, "Failed to get class codes by tin"))
        assert exc.status_code == 503
        assert exc.detail == "didox_ikpu_unavailable"

    def test_an_ordinary_rejection_stays_a_422(self) -> None:
        from app.domains.marketplace.api_portal_ikpu import _provider_error
        from app.integrations.didox import DidoxError

        exc = _provider_error(DidoxError(422, "Неподдерживаемый код"))
        assert exc.status_code == 422


def test_the_picker_routes_are_mounted() -> None:
    from app.main import create_app

    paths = set(create_app().openapi()["paths"])
    assert "/api/v1/portal/ikpu/search" in paths
    assert "/api/v1/portal/companies/{company_id}/ikpu/{class_code}/packages" in paths
    assert "/api/v1/portal/companies/{company_id}/ikpu/{class_code}/bind" in paths


# ── «when did we last take this from Didox» ───────────────────────────────────


class TestSyncedAt:
    """`ikpu_synced_at` is the only record of WHEN the code was read off Didox.

    It shipped as a column nothing ever wrote, so every offer carried a NULL that
    read as "never synced" — which is exactly what it would say about a stale code
    too. A column that is always NULL cannot answer the question it exists for.
    """

    def test_a_code_stamps_the_sync_time(self) -> None:
        from app.domains.marketplace.service import _ikpu_synced_at

        assert _ikpu_synced_at(ikpu_code="03901001001000000") is not None

    def test_no_code_means_no_stamp(self) -> None:
        """Clearing the code clears the timestamp — a sync time with nothing
        synced is a lie about evidence we do not have."""
        from app.domains.marketplace.service import _ikpu_synced_at

        assert _ikpu_synced_at(ikpu_code=None) is None

    def test_both_save_paths_stamp_it(self) -> None:
        """A helper nothing calls is the bug this class exists for."""
        import inspect

        from app.domains.marketplace import service

        for fn in (service.create_company_offer, service.update_company_offer):
            assert "_ikpu_synced_at" in inspect.getsource(fn)


# ── the edit round trip ───────────────────────────────────────────────────────


class TestEditRoundTrip:
    """A field the READ omits is a field the next EDIT deletes.

    The offer form hydrates from `CompanyOfferOut` and PUTs the whole draft back,
    so anything missing from that schema comes back as `None` and is written over
    the stored value. For the ИКПУ that means a seller who fixes a typo in their
    description silently loses the tax classification of their goods — and finds
    out at contract time. Same shape for the sample-letter pair.
    """

    def test_the_read_schema_carries_every_field_the_write_schema_takes(self) -> None:
        from app.domains.companies.schemas import CompanyOfferIn, CompanyOfferOut

        written = set(CompanyOfferIn.model_fields)
        read = set(CompanyOfferOut.model_fields)
        assert written - read == set(), f"edit would erase: {sorted(written - read)}"

    def test_ikpu_survives_a_round_trip(self) -> None:
        from app.domains.companies.schemas import CompanyOfferIn, CompanyOfferOut

        class _Row:
            def __init__(self) -> None:
                self.id, self.status = 93, "pending_moderation"
                self.availability, self.qty_unit = "in_stock", "MT"
                self.currency, self.incoterms = "USD", "EXW"
                import datetime as _dt

                self.created_at = _dt.datetime(2026, 8, 21, tzinfo=_dt.UTC)
                for key, value in COMPLETE.items():
                    setattr(self, key, value)

        out = CompanyOfferOut.model_validate(_Row(), from_attributes=True)
        again = CompanyOfferIn(**{k: getattr(out, k) for k in COMPLETE})
        assert again.ikpu_code == COMPLETE["ikpu_code"]
        assert again.ikpu_origin == COMPLETE["ikpu_origin"]
