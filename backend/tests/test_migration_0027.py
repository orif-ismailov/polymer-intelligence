"""
Offline tests for migration 0027: chemical compliance (P5 W1 — T1.1).

One migration for one bounded context. It brings in:

1. `substances` — our own registry of regulated chemistry. There is no
   machine-readable state registry in Uzbekistan (INTEGRATIONS.md §4), so this
   table IS the source of truth, digitized from the ПКМ lists. The legal
   identifier is the HS/ТН ВЭД code — the official lists are written in names +
   HS codes, not CAS — so `hs_code` is NOT NULL while `cas` is a nullable
   secondary key used for AI matching and international SDS.
2. `company_licenses` — what a company is allowed to trade, per REGIME. The four
   regimes have four different licensors; "holds a licence" without a regime
   would let an ecology certificate unlock precursor sales.
3. `substance_suggestions` — the journal of AI hints (FR-C3). A suggestion is
   never written into the offer on its own; the seller confirms it, and
   `accepted IS NULL` means nobody has decided yet.
4. `seller_offers` gains the substance link, the manually-typed CAS/HS pair, the
   declared concentration (regulation is concentration-dependent: acetone is a
   precursor at ≥60%, not below), and a CACHE of the verdict so a list screen
   does not re-evaluate every row.

(`app.*` is imported inside the tests: the conftest env patch is a session
fixture and does not exist at collection time.)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0027_compliance.py"


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0027", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


def _metadata():  # noqa: ANN202
    import app.models  # noqa: F401, PLC0415
    from app.core.db import Base  # noqa: PLC0415

    return Base.metadata


class TestRevisionChain:
    def test_revision_and_down_revision(self) -> None:
        module = _load_migration()
        assert module.revision == "0027"
        assert module.down_revision == "0026"

    def test_upgrade_downgrade_callable(self) -> None:
        module = _load_migration()
        assert callable(module.upgrade)
        assert callable(module.downgrade)


class TestEnums:
    def test_regulation_levels(self) -> None:
        from app.models.enums import RegulationLevel  # noqa: PLC0415

        assert [m.value for m in RegulationLevel] == [
            "free",
            "docs_required",
            "license_required",
            "prohibited",
        ]

    def test_regulation_regimes_are_the_four_uzbek_acts(self) -> None:
        """Each regime has its own licensor and its own document set — ПКМ-330
        (Список IV precursors), ПКМ-782+397, ПКМ-818, ПКМ-916."""
        from app.models.enums import RegulationRegime  # noqa: PLC0415

        assert [m.value for m in RegulationRegime] == [
            "precursor_list_iv",
            "explosive_toxic",
            "strong_acting",
            "pkm916_import",
        ]

    def test_license_statuses(self) -> None:
        from app.models.enums import LicenseStatus  # noqa: PLC0415

        assert [m.value for m in LicenseStatus] == [
            "pending_review",
            "active",
            "expired",
            "revoked",
            "rejected",
        ]

    def test_offer_file_kind_covers_the_documents_the_lists_ask_for(self) -> None:
        """`required_docs` on a substance names SDS/TDS/COA. Without the enum
        values there is nothing for the docs_required verdict to look at."""
        from app.models.enums import OfferFileKind  # noqa: PLC0415

        values = {m.value for m in OfferFileKind}
        assert {"sds", "tds", "coa"} <= values

    def test_migration_adds_enum_values_outside_a_transaction(self) -> None:
        """ALTER TYPE … ADD VALUE cannot run inside a transaction block."""
        source = _MIGRATION.read_text(encoding="utf-8")
        assert "autocommit_block" in source
        assert "ADD VALUE IF NOT EXISTS 'sds'" in source
        assert "ADD VALUE IF NOT EXISTS 'coa'" in source


class TestSubstances:
    def test_registered(self) -> None:
        assert "substances" in _metadata().tables

    def test_hs_code_is_the_legal_identifier_and_cas_is_secondary(self) -> None:
        """The official ПКМ lists are written as names + ТН ВЭД codes. CAS is for
        AI matching and international SDS, so it may be missing."""
        substances = _metadata().tables["substances"]
        assert substances.c.hs_code.nullable is False
        assert substances.c.cas.nullable is True

    def test_code_and_cas_are_unique(self) -> None:
        substances = _metadata().tables["substances"]
        for column in ("code", "cas"):
            assert substances.c[column].unique, (
                f"{column} must be unique — the seed is idempotent on code, and two "
                f"rows for one CAS would give two different verdicts"
            )

    def test_regulation_is_concentration_and_volume_aware(self) -> None:
        """Список IV regulates acetone at ≥60% and exempts ≤12 kg/year — a bare
        level would over-block ordinary industrial chemistry."""
        substances = _metadata().tables["substances"]
        for column in (
            "threshold_concentration_pct",
            "exemption_annual_limit",
            "exemption_unit",
        ):
            assert column in substances.c

    def test_carries_its_legal_source_and_seed_revision(self) -> None:
        """Every row must answer "on what act, and from which digitization?" — the
        lists get re-issued and the seed is versioned."""
        substances = _metadata().tables["substances"]
        assert "source_act" in substances.c
        assert "seed_revision" in substances.c


class TestCompanyLicenses:
    def test_registered(self) -> None:
        assert "company_licenses" in _metadata().tables

    def test_a_licence_is_per_regime(self) -> None:
        licenses = _metadata().tables["company_licenses"]
        assert licenses.c.regime.nullable is False, (
            "a licence without a regime would satisfy any gate"
        )

    def test_expiry_and_revocation_are_recorded_not_inferred(self) -> None:
        licenses = _metadata().tables["company_licenses"]
        for column in ("expires_at", "revoked_at", "revoke_reason"):
            assert column in licenses.c

    def test_evidence_survives_the_document_being_removed(self) -> None:
        """The licence row is the decision; its evidence document is a pointer."""
        licenses = _metadata().tables["company_licenses"]
        fks = [
            fk
            for fk in licenses.foreign_keys
            if fk.column.table.name == "verification_documents"
        ]
        assert fks and fks[0].ondelete == "SET NULL"

    def test_a_deleted_company_takes_its_licences_with_it(self) -> None:
        licenses = _metadata().tables["company_licenses"]
        fks = [fk for fk in licenses.foreign_keys if fk.column.table.name == "companies"]
        assert fks and fks[0].ondelete == "CASCADE"


class TestSubstanceSuggestions:
    def test_registered(self) -> None:
        assert "substance_suggestions" in _metadata().tables

    def test_journals_the_model_and_prompt_version(self) -> None:
        """Same convention as parse_runs: a suggestion is replayable only if we
        know which prompt version produced it."""
        suggestions = _metadata().tables["substance_suggestions"]
        assert suggestions.c.model.nullable is False
        assert suggestions.c.prompt_version.nullable is False

    def test_undecided_is_a_real_state(self) -> None:
        """FR-C3: never auto-written. NULL = the seller has not answered yet,
        which is different from "rejected"."""
        suggestions = _metadata().tables["substance_suggestions"]
        assert suggestions.c.accepted.nullable is True

    def test_can_be_made_before_the_offer_exists(self) -> None:
        """The hint is asked for while the form is being filled in."""
        suggestions = _metadata().tables["substance_suggestions"]
        assert suggestions.c.offer_id.nullable is True


class TestSellerOfferComplianceColumns:
    def test_columns_registered(self) -> None:
        offers = _metadata().tables["seller_offers"]
        for column in (
            "substance_id",
            "cas_number",
            "hs_code",
            "declared_concentration_pct",
            "compliance_level",
            "compliance_ok",
            "compliance_missing",
            "compliance_checked_at",
        ):
            assert column in offers.c, f"seller_offers.{column} missing"

    def test_every_new_column_is_safe_on_a_live_table(self) -> None:
        offers = _metadata().tables["seller_offers"]
        for column in (
            "substance_id",
            "cas_number",
            "hs_code",
            "declared_concentration_pct",
            "compliance_level",
            "compliance_ok",
            "compliance_missing",
            "compliance_checked_at",
        ):
            spec = offers.c[column]
            assert spec.nullable or spec.server_default is not None, (
                f"{column} is NOT NULL with no server default"
            )

    def test_deactivating_a_substance_does_not_delete_offers(self) -> None:
        offers = _metadata().tables["seller_offers"]
        fks = [fk for fk in offers.foreign_keys if fk.column.table.name == "substances"]
        assert fks and fks[0].ondelete == "SET NULL", (
            "removing a registry row must not take live offers with it"
        )


class TestSingleHead:
    def test_0027_is_the_head(self) -> None:
        script = _script_dir()
        assert script.get_heads() == ["0027"], (
            f"expected a single head 0027, got {script.get_heads()}"
        )
