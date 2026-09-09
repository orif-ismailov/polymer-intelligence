"""Contract-template authoring: validation, versioning, and the shipped bodies.

`render._fill` substitutes `context.get(name, "")`, so a `{{ name }}` the renderer
cannot supply becomes an EMPTY STRING — no exception, no log line, and no leftover
`{{ }}` in the output to notice. The result is a legally binding document with a
hole in it, and the only way to find out is to read the PDF.

`TestShippedTemplatesRender` is the test that matters most here. It caught a live
one: `SAMPLE_LETTER_V1` wrote `{{ buyer_legal_name }}` / `{{ seller_inn }}` while
the renderer produces `initiator_*` / `counterparty_*`, so every commitment letter
this platform generated identified NEITHER party — no name, no INN, no address, no
director, on both sides. Eight placeholders, silently blank.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.domains.contracts import templates as template_service
from app.domains.contracts.render import render_contract_html

_SEED_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "seed" / "data"
_BODIES = _SEED_DIR / "contract_templates"

_CONTRACT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["product"],
    "properties": {"product": {"type": "string", "title": "Товар"}},
}


class TestValidateBody:
    def test_accepts_every_renderable_name(self) -> None:
        body = (
            "<p>{{ contract_public_id }} {{ generated_at }} {{ title }} "
            "{{ initiator_legal_name }} {{ counterparty_bank_mfo }} {{ product }}</p>"
        )
        report = template_service.validate_body(body, "contract", _CONTRACT_SCHEMA)
        assert report.ok
        assert report.unknown == []

    def test_refuses_a_name_the_renderer_cannot_fill(self) -> None:
        """The whole point: this is the difference between a refused save and a
        contract that prints a blank where the buyer's name should be."""
        body = "<p>{{ product }} {{ buyer_nmae }}</p>"
        report = template_service.validate_body(body, "contract", _CONTRACT_SCHEMA)
        assert not report.ok
        assert report.unknown == ["buyer_nmae"]

    def test_a_letter_has_no_bank_fields(self) -> None:
        """`lab_orders.letters._requisites` deliberately omits bank details, so a
        letter body asking for one would render blank."""
        body = "<p>{{ initiator_bank_account }}</p>"
        assert not template_service.validate_body(body, "sample_letter", {}).ok
        assert template_service.validate_body(body, "contract", {}).ok

    def test_a_letter_has_no_title(self) -> None:
        """`title` is added by `contract_service._render_and_store`, not by the
        letter renderer."""
        assert not template_service.validate_body("{{ title }}", "sample_letter", {}).ok
        assert template_service.validate_body("{{ title }}", "contract", {}).ok

    def test_warns_about_a_self_numbered_section(self) -> None:
        """Didox prefixes its own `ordno` when it prints, so «1. Стороны» came out
        as «1. 1. Стороны» on the operator's form. A warning, not a refusal."""
        report = template_service.validate_body("<h2>1. Стороны</h2>", "contract", {})
        assert report.ok, "a numbering nit must not block a save"
        assert any("starts with its own number" in w for w in report.warnings)

    def test_a_year_is_not_mistaken_for_an_ordinal(self) -> None:
        """The separator in `_LEADING_ORDINAL` is required: «2026 год» has none."""
        report = template_service.validate_body("<h2>2026 год итоги</h2>", "contract", {})
        assert not any("starts with its own number" in w for w in report.warnings)

    def test_warns_about_an_unused_schema_key(self) -> None:
        report = template_service.validate_body("<p>hi</p>", "contract", _CONTRACT_SCHEMA)
        assert report.ok
        assert any("never used in the body" in w for w in report.warnings)


class TestRenderableNamesMatchTheRenderer:
    """Pins the validator to what `render_contract_html` ACTUALLY injects.

    Without this the allowed-name set is a hand-copied list that goes stale the
    first time a requisites field is added — and a stale list is worse than none,
    because it refuses a placeholder that would have worked, or admits one that
    silently renders blank.
    """

    @pytest.mark.parametrize("kind", ["contract", "sample_letter"])
    def test_every_allowed_name_actually_resolves(self, kind: str) -> None:
        names = template_service.renderable_names(kind, _CONTRACT_SCHEMA)
        body = " ".join(f"[{n}:{{{{ {n} }}}}]" for n in sorted(names))

        html = template_service.preview(body, kind, _CONTRACT_SCHEMA)

        empty = re.findall(r"\[(\w+):\]", html)
        assert not empty, f"renderer supplies nothing for: {empty}"

    def test_requisite_keys_match_the_contract_builder(self) -> None:
        """`REQUISITE_KEYS` must equal what `_requisites` returns, or the validator
        drifts from the renderer the moment a field is added."""
        from app.domains.contracts.service import REQUISITE_KEYS, _requisites  # noqa: PLC0415

        company = _StubCompany()
        keys = set(_requisites(_StubSession(), company).keys())  # type: ignore[arg-type]

        assert keys == set(REQUISITE_KEYS)

    def test_requisite_keys_match_the_letter_builder(self) -> None:
        from app.domains.lab_orders.letters import REQUISITE_KEYS, _requisites  # noqa: PLC0415

        keys = set(_requisites(_StubSession(), _StubCompany()).keys())  # type: ignore[arg-type]

        assert keys == set(REQUISITE_KEYS)


class TestShippedTemplatesRender:
    """Every body the seeder installs must be fully renderable.

    This is the guard that was missing. `SAMPLE_LETTER_V1` shipped with eight
    placeholders the renderer never produced, and nothing anywhere said so — the
    PDF simply came out with both parties' identity blocks empty.
    """

    @pytest.mark.parametrize(
        ("filename", "kind"),
        [
            ("supply_v1_ru.html", "contract"),
            ("supply_v2_ru.html", "contract"),
            ("sample_letter_v1_ru.html", "sample_letter"),
        ],
    )
    def test_no_unrenderable_placeholders(self, filename: str, kind: str) -> None:
        from app.seed import seed_contract_templates as seeder  # noqa: PLC0415

        schemas = {
            "supply_v1_ru.html": seeder._SUPPLY_V1_SCHEMA,
            "supply_v2_ru.html": seeder._SUPPLY_V2_SCHEMA,
            "sample_letter_v1_ru.html": seeder._SAMPLE_LETTER_V1_SCHEMA,
        }
        body = (_BODIES / filename).read_text(encoding="utf-8")

        report = template_service.validate_body(body, kind, schemas[filename])

        assert report.ok, f"{filename} uses names the renderer cannot fill: {report.unknown}"

    def test_the_letter_names_both_parties(self) -> None:
        """The specific regression, asserted on rendered output rather than on the
        placeholder list — an empty `<td>` is what a reader would actually see."""
        body = (_BODIES / "sample_letter_v1_ru.html").read_text(encoding="utf-8")
        buyer: dict[str, object] = {
            "legal_name": "ООО «ПОКУПАТЕЛЬ»",
            "inn": "312616547",
            "address": "г. Ташкент",
            "director": "Иванов И.И.",
        }
        seller: dict[str, object] = {
            "legal_name": "АО «ПРОДАВЕЦ»",
            "inn": "207654321",
            "address": "г. Навои",
            "director": "Петров П.П.",
        }

        # Only the SCHEMA variables. `render_contract_html` applies `variables`
        # last, so passing every placeholder here would overwrite the very party
        # values under test with the filler — which is what a first draft of this
        # test did, and it failed for that reason rather than for a real one.
        from app.seed.seed_contract_templates import _SAMPLE_LETTER_V1_SCHEMA  # noqa: PLC0415

        properties = _SAMPLE_LETTER_V1_SCHEMA["properties"]
        assert isinstance(properties, dict)
        html = render_contract_html(
            body,
            dict.fromkeys(properties, "—"),
            buyer,
            seller,
            contract_public_id="abc",
            generated_at="2026-01-01 00:00 UTC",
        )

        for expected in ("ООО «ПОКУПАТЕЛЬ»", "312616547", "АО «ПРОДАВЕЦ»", "207654321"):
            assert expected in html, f"the letter does not name {expected!r}"


class TestPreview:
    def test_fills_with_visible_stand_ins(self) -> None:
        """Realistic sample values would HIDE a missing placeholder, which is the
        failure being guarded against. A hole in this output is a real hole."""
        html = template_service.preview(
            "<p>{{ initiator_legal_name }} — {{ product }}</p>", "contract", _CONTRACT_SCHEMA
        )
        assert "[initiator_legal_name]" in html
        assert "[Товар]" in html, "a declared title is friendlier than the raw key"

    def test_leaves_an_unrenderable_name_visibly_empty(self) -> None:
        html = template_service.preview("<p>[{{ buyer_nmae }}]</p>", "contract", {})
        assert "[]" in html


class _StubCompany:
    """Just the attributes `_requisites` reads."""

    id = 1
    legal_name = "ООО Т"
    tax_id = "123456789"
    legal_address = "адрес"
    director_name = "директор"


class _StubQuery:
    def filter(self, *a: object, **k: object) -> _StubQuery:
        return self

    def order_by(self, *a: object, **k: object) -> _StubQuery:
        return self

    def first(self) -> None:
        return None


class _StubSession:
    def query(self, *a: object, **k: object) -> _StubQuery:
        return _StubQuery()
