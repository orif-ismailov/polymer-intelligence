"""
Compliance verdicts — the decision table (P5 W3 — T3.1). No database.

`offer_compliance_service.decide()` is the whole ruleset as a pure function, so
the rules can be read as a table instead of being reconstructed from SQL. The DB
half (finding the substance, finding an active licence) is tested separately in
test_offer_compliance_gate_db.py.

The four rules that carry the most weight:

  * **`prohibited` is not negotiable.** No document, licence or concentration
    makes a banned substance publishable — the ПКМ-916 lists are bans, not
    paperwork requirements.
  * **Concentration decides whether a regime applies at all.** Список IV catches
    acetone at ≥60%; at 20% it is a solvent. Getting this wrong blocks half of
    ordinary industrial chemistry.
  * **A missing declaration is treated as regulated.** "Concentration unknown"
    must not be a way through the gate.
  * **Documents and a licence are checked independently.** A substance can
    require both, and "I uploaded an SDS" is not a licence.

(`app.*` is imported inside the tests: the conftest env patch is a session
fixture and does not exist at collection time.)
"""

from __future__ import annotations

import decimal

import pytest


def _decide(**kwargs):  # noqa: ANN003, ANN202
    from app.domains.marketplace import compliance as svc  # noqa: PLC0415
    from app.models.enums import RegulationLevel  # noqa: PLC0415

    params = {
        "level": RegulationLevel.free,
        "regime": None,
        "required_docs": (),
        "threshold_concentration_pct": None,
        "declared_concentration_pct": None,
        "attached_doc_kinds": frozenset(),
        "has_license": False,
        "source_act": None,
    }
    params.update(kwargs)
    return svc.decide(**params)


def _dec(value: str) -> decimal.Decimal:
    return decimal.Decimal(value)


class TestFree:
    def test_an_unregulated_substance_publishes(self) -> None:
        verdict = _decide()
        assert verdict.ok is True
        assert verdict.missing == ()

    def test_free_ignores_attached_documents(self) -> None:
        verdict = _decide(attached_doc_kinds=frozenset({"sds"}))
        assert verdict.ok is True


class TestDocsRequired:
    def test_missing_documents_block_and_are_named(self) -> None:
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.docs_required,
            regime=RegulationRegime.pkm916_import,
            required_docs=("certificate", "sds"),
            attached_doc_kinds=frozenset({"sds"}),
        )
        assert verdict.ok is False
        assert [(m.kind, m.detail) for m in verdict.missing] == [("document", "certificate")]

    def test_all_documents_present_publishes(self) -> None:
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.docs_required,
            regime=RegulationRegime.pkm916_import,
            required_docs=("certificate",),
            attached_doc_kinds=frozenset({"certificate", "image"}),
        )
        assert verdict.ok is True


class TestLicenseRequired:
    def test_no_licence_blocks_and_names_the_regime(self) -> None:
        """The regime is what the seller has to go and get — "a licence" is not
        an actionable instruction when four different bodies issue them."""
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.license_required,
            regime=RegulationRegime.precursor_list_iv,
            has_license=False,
        )
        assert verdict.ok is False
        assert [(m.kind, m.detail) for m in verdict.missing] == [
            ("license", "precursor_list_iv")
        ]

    def test_holding_the_licence_publishes(self) -> None:
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.license_required,
            regime=RegulationRegime.precursor_list_iv,
            has_license=True,
        )
        assert verdict.ok is True

    def test_documents_do_not_substitute_for_a_licence(self) -> None:
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.license_required,
            regime=RegulationRegime.precursor_list_iv,
            required_docs=("sds",),
            attached_doc_kinds=frozenset({"sds"}),
            has_license=False,
        )
        assert verdict.ok is False
        assert [m.kind for m in verdict.missing] == ["license"]

    def test_a_licence_does_not_substitute_for_documents(self) -> None:
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.license_required,
            regime=RegulationRegime.precursor_list_iv,
            required_docs=("sds",),
            attached_doc_kinds=frozenset(),
            has_license=True,
        )
        assert verdict.ok is False
        assert [m.kind for m in verdict.missing] == ["document"]


class TestProhibited:
    @pytest.mark.parametrize(
        ("docs", "licensed"),
        [(frozenset(), False), (frozenset({"sds", "certificate", "coa"}), True)],
    )
    def test_nothing_unblocks_it(self, docs: frozenset[str], licensed: bool) -> None:
        """ПКМ-916 bans are bans. This is the one verdict that no upload changes."""
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.prohibited,
            regime=RegulationRegime.pkm916_import,
            required_docs=("sds",),
            attached_doc_kinds=docs,
            has_license=licensed,
            source_act="ПКМ №916",
        )
        assert verdict.ok is False
        assert [(m.kind, m.detail) for m in verdict.missing] == [("prohibited", "ПКМ №916")]

    def test_a_low_concentration_does_not_unban_it(self) -> None:
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.prohibited,
            regime=RegulationRegime.pkm916_import,
            threshold_concentration_pct=_dec("60"),
            declared_concentration_pct=_dec("1"),
        )
        assert verdict.ok is False
        assert verdict.exempt_reason is None


class TestConcentrationThreshold:
    def test_below_the_threshold_the_regime_does_not_apply(self) -> None:
        """Acetone at 20% is a solvent, not a Список IV precursor."""
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.license_required,
            regime=RegulationRegime.precursor_list_iv,
            threshold_concentration_pct=_dec("60"),
            declared_concentration_pct=_dec("20"),
            has_license=False,
        )
        assert verdict.ok is True
        assert verdict.exempt_reason == "below_threshold"
        assert verdict.level == RegulationLevel.free

    def test_at_the_threshold_it_applies(self) -> None:
        """Список IV says "≥60%", so exactly 60 is regulated."""
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.license_required,
            regime=RegulationRegime.precursor_list_iv,
            threshold_concentration_pct=_dec("60"),
            declared_concentration_pct=_dec("60"),
            has_license=False,
        )
        assert verdict.ok is False

    def test_an_undeclared_concentration_is_treated_as_regulated(self) -> None:
        """Otherwise leaving the field blank is the way past the gate."""
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.license_required,
            regime=RegulationRegime.precursor_list_iv,
            threshold_concentration_pct=_dec("60"),
            declared_concentration_pct=None,
            has_license=False,
        )
        assert verdict.ok is False
        assert verdict.exempt_reason is None

    def test_a_substance_without_a_threshold_is_regulated_at_any_strength(self) -> None:
        """Acetic anhydride is on Список IV with no threshold at all."""
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.license_required,
            regime=RegulationRegime.precursor_list_iv,
            threshold_concentration_pct=None,
            declared_concentration_pct=_dec("1"),
            has_license=False,
        )
        assert verdict.ok is False


class TestSerialization:
    def test_missing_serializes_to_the_cached_shape(self) -> None:
        """The verdict is cached on the offer as JSONB and read back by two
        frontends, so its shape is part of the contract."""
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        verdict = _decide(
            level=RegulationLevel.license_required,
            regime=RegulationRegime.precursor_list_iv,
            required_docs=("sds",),
        )
        assert verdict.as_json() == [
            {"kind": "document", "detail": "sds"},
            {"kind": "license", "detail": "precursor_list_iv"},
        ]
