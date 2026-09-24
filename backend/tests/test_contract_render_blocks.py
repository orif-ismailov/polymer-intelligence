"""The template engine's two additions for the real supply contracts (24.09.2026).

The MGBUS contracts differ by a handful of clauses — prepayment or a payment
schedule, a packaging section or none — so a template carries every variant and
the user's switches pick one. Two mechanisms, both pure:

  * `{{#if key}}…{{/if}}`, `{{#if key=value}}…{{/if}}`, `{{#if key!=value}}…{{/if}}`;
  * numbering by the renderer (`data-n` on `<h2>` and on clause `<p>`), so a
    switched-off section or clause leaves no hole in «3 → 5» or «2.2 → 2.4».
"""

from __future__ import annotations

from app.domains.contracts import render as contract_render


def _render(body: str, **variables: object) -> str:
    return contract_render.render_contract_html(
        body, variables, {}, {}, contract_public_id="x", generated_at="t"
    )


class TestConditionalBlocks:
    def test_equality_picks_the_variant(self) -> None:
        body = (
            "{{#if payment_mode=prepay}}<p>Предоплата 100%</p>{{/if}}"
            "{{#if payment_mode=schedule}}<p>По графику</p>{{/if}}"
        )
        assert _render(body, payment_mode="prepay") == "<p>Предоплата 100%</p>"
        assert _render(body, payment_mode="schedule") == "<p>По графику</p>"

    def test_inequality(self) -> None:
        body = "{{#if packaging!=none}}<p>Тара</p>{{/if}}"
        assert _render(body, packaging="bulk") == "<p>Тара</p>"
        assert _render(body, packaging="none") == ""

    def test_truthiness(self) -> None:
        body = "{{#if quality_section}}<p>Качество</p>{{/if}}"
        assert _render(body, quality_section="true") == "<p>Качество</p>"
        for off in ("", "false", "0", "no"):
            assert _render(body, quality_section=off) == ""
        assert _render(body) == ""

    def test_placeholders_inside_a_block_are_filled(self) -> None:
        body = "{{#if payment_mode=prepay}}<p>{{ refuse_after_days }} дн.</p>{{/if}}"
        assert _render(body, payment_mode="prepay", refuse_after_days="1") == "<p>1 дн.</p>"

    def test_blocks_nest(self) -> None:
        body = "{{#if a=1}}<p>A</p>{{#if b}}<p>B</p>{{/if}}<p>C</p>{{/if}}<p>D</p>"
        assert _render(body, a="1", b="yes") == "<p>A</p><p>B</p><p>C</p><p>D</p>"
        assert _render(body, a="1", b="no") == "<p>A</p><p>C</p><p>D</p>"
        assert _render(body, a="2", b="yes") == "<p>D</p>"

    def test_a_block_spans_lines(self) -> None:
        body = "{{#if quality_section}}\n<h2>Качество</h2>\n<p>текст</p>\n{{/if}}"
        assert "<h2>Качество</h2>" in _render(body, quality_section="true")


class TestNumbering:
    def test_sections_and_clauses_are_numbered_in_order(self) -> None:
        body = (
            "<h2 data-n>ПРЕДМЕТ</h2><p data-n>a</p><p data-n>b</p>"
            "<h2 data-n>УСЛОВИЯ</h2><p data-n>c</p>"
        )
        out = _render(body)
        assert "<h2>1. ПРЕДМЕТ</h2>" in out
        assert "<p>1.1. a</p><p>1.2. b</p>" in out
        assert "<h2>2. УСЛОВИЯ</h2><p>2.1. c</p>" in out

    def test_a_switched_off_section_leaves_no_hole(self) -> None:
        body = (
            "<h2 data-n>ОТВЕТСТВЕННОСТЬ</h2>"
            "{{#if packaging!=none}}<h2 data-n>ТАРА</h2><p data-n>наливом</p>{{/if}}"
            "<h2 data-n>СРОК</h2><p data-n>до исполнения</p>"
        )
        out = _render(body, packaging="none")
        assert "<h2>2. СРОК</h2><p>2.1. до исполнения</p>" in out
        assert "ТАРА" not in out

    def test_a_switched_off_clause_leaves_no_hole(self) -> None:
        body = (
            "<h2 data-n>УСЛОВИЯ</h2><p data-n>стоимость</p>"
            "{{#if payment_mode=schedule}}<p data-n>график</p>{{/if}}"
            "<p data-n>просрочка</p>"
        )
        assert "<p>1.2. просрочка</p>" in _render(body, payment_mode="prepay")
        assert "<p>1.3. просрочка</p>" in _render(body, payment_mode="schedule")

    def test_unnumbered_markup_is_left_alone(self) -> None:
        assert _render("<h2>1. Стороны</h2><p>текст</p>") == "<h2>1. Стороны</h2><p>текст</p>"

    def test_numbered_elements_keep_their_other_attributes(self) -> None:
        out = _render('<h2 data-n class="x">A</h2><p class="clause" data-n>b</p>')
        assert '<h2 class="x">1. A</h2>' in out
        assert '<p class="clause">1.1. b</p>' in out


class TestValidatorKnowsTheBlocks:
    def test_the_condition_key_counts_as_used(self) -> None:
        from app.domains.contracts import templates  # noqa: PLC0415

        schema = {"properties": {"payment_mode": {"enum": ["prepay", "schedule"]}}}
        report = templates.validate_body(
            "{{#if payment_mode=prepay}}<p>x</p>{{/if}}", "contract", schema
        )
        assert report.ok
        assert report.unknown == []

    def test_an_unknown_condition_key_is_refused(self) -> None:
        from app.domains.contracts import templates  # noqa: PLC0415

        report = templates.validate_body("{{#if nope}}<p>x</p>{{/if}}", "contract", {})
        assert not report.ok
        assert "nope" in report.unknown

    def test_an_unbalanced_block_is_refused(self) -> None:
        from app.domains.contracts import templates  # noqa: PLC0415

        schema = {"properties": {"a": {}, "b": {}}}
        unclosed = templates.validate_body("{{#if a}}<p>x</p>", "contract", schema)
        stray = templates.validate_body("<p>x</p>{{/if}}{{#if a}}", "contract", schema)
        nested = templates.validate_body(
            "{{#if a}}{{#if b}}<p>x</p>{{/if}}{{/if}}", "contract", schema
        )
        assert not unclosed.ok
        assert not stray.ok
        assert nested.ok


class TestSupplierAndBuyer:
    """The real contracts name «Поставщик» and «Покупатель», not the initiator."""

    def test_the_initiator_supplies_by_default(self) -> None:
        out = contract_render.render_contract_html(
            "{{ supplier_legal_name }} → {{ buyer_legal_name }}", {},
            {"legal_name": "MGBUS"}, {"legal_name": "AKFA"},
            contract_public_id="x", generated_at="t",
        )
        assert out == "MGBUS → AKFA"

    def test_a_buyer_can_draw_up_the_contract(self) -> None:
        out = contract_render.render_contract_html(
            "{{ supplier_legal_name }} → {{ buyer_legal_name }}", {"initiator_side": "buyer"},
            {"legal_name": "AKFA"}, {"legal_name": "MGBUS"},
            contract_public_id="x", generated_at="t",
        )
        assert out == "MGBUS → AKFA"


class TestDerivedValues:
    def test_a_one_off_contract_carries_its_specification_totals(self) -> None:
        out = _render(
            "{{ spec_amount_with_vat }}|{{ spec_vat_sum }}|{{ spec_price_without_vat }}|"
            "{{ amount_total_phrase }}",
            contract_kind="one_off", qty="120000", price_with_vat="16300", vat_rate="12",
        )
        assert out == (
            "1 956 000 000|209 571 428,57|14 553,57|"
            "1 956 000 000 (один миллиард девятьсот пятьдесят шесть миллионов) сум 00 тийин"
        )

    def test_a_frame_contract_states_its_limit(self) -> None:
        out = _render("{{ amount_total_phrase }}", contract_kind="frame", amount_limit="20000000000")
        assert out == "20 000 000 000 (двадцать миллиардов) сум 00 тийин"

    def test_numbers_that_do_not_parse_leave_the_totals_empty(self) -> None:
        assert _render("[{{ spec_amount_with_vat }}]", qty="много", price_with_vat="1") == "[]"
