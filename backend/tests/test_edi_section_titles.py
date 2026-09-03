"""Didox numbers the sections; we must not number them too.

Visible the moment the operator's printed form was put on screen (27.08.2026):

    1. 1. Стороны
    2. 2. Предмет договора
    3. 3. Подписи сторон

Our template writes «1. Стороны» into the `<h2>`, `sections_from_html` carries it
through verbatim, and Didox then prefixes its own `ordno`. Both are behaving
correctly; the ownership of the number was never decided. It is theirs — the
order on their form is `ordno`, and a number of ours that disagreed with it would
be worse than a duplicated one.

Only a LEADING ordinal goes. A title that merely contains a number («Приложение
№2 к договору») keeps it, because that is part of the name rather than its
position.
"""

from __future__ import annotations

import pytest


class TestTheLeadingOrdinalIsDropped:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1. Стороны", "Стороны"),
            ("2. Предмет договора", "Предмет договора"),
            ("10. Заключительные положения", "Заключительные положения"),
            ("1) Стороны", "Стороны"),
            ("1.2. Порядок расчётов", "Порядок расчётов"),
            # No leading ordinal — untouched.
            ("Стороны", "Стороны"),
            ("Приложение №2 к договору", "Приложение №2 к договору"),
            # A bare number is not a numbering: the separator is what makes it
            # one, and without that rule this loses its year.
            ("2026 год: особые условия", "2026 год: особые условия"),
            ("1 Стороны", "1 Стороны"),
        ],
    )
    def test_titles(self, raw: str, expected: str) -> None:
        from app.domains.edi.contract_docs import _strip_leading_ordinal

        assert _strip_leading_ordinal(raw) == expected

    def test_a_title_that_is_only_a_number_survives(self) -> None:
        """Stripping it would leave an empty heading, which reads worse than a
        redundant one."""
        from app.domains.edi.contract_docs import _strip_leading_ordinal

        assert _strip_leading_ordinal("1.") == "1."

    def test_sections_come_out_unnumbered(self) -> None:
        from app.domains.edi.contract_docs import sections_from_html

        html = (
            "<h1>ДОГОВОР ПОСТАВКИ</h1>"
            "<h2>1. Стороны</h2><p>Продавец и Покупатель.</p>"
            "<h2>2. Предмет договора</h2><p>Поставка полимеров.</p>"
        )
        assert sections_from_html(html) == [
            ("Стороны", "Продавец и Покупатель."),
            ("Предмет договора", "Поставка полимеров."),
        ]
