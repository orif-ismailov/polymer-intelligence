"""The registry's legal-form wording → the six forms the registration form offers.

Why this exists. `companies.legal_form` is free text, and the portal's
«Форма собственности» select carries six short codes (`ООО`, `ЧП`, `АО`, `СП`,
`ИП`, `ГУП`) whose *value* is the code and whose *label* is the full name. When
a value arrives that is none of those six, `StepDetails.tsx` appends it as a
seventh option labelled with its raw string — deliberately, so an unrecognised
row is never silently rewritten.

The state registry then walked straight into that branch. Didox returns its own
wording in `na1Name` — the captured record says «Общество с огр. ответствен.» —
so prefilling an ИНН produced a select with TWO entries meaning "LLC": ours and
the registry's, differing only in spelling. Whichever the registry supplied was
also auto-selected, so the stored value drifted off the vocabulary too.

So the wording is mapped onto the code before it reaches the form. Two rules the
tests below hold in place:

  * **An unrecognised wording is returned UNCHANGED.** Guessing would rewrite a
    real company's legal form into a neighbouring one, and the append-a-seventh
    -option branch is the correct destination for anything we cannot place.
  * **Every code this can return is one the select actually offers.** The list
    lives in the portal; a target that is not on it re-creates the bug the
    mapping was written to remove, so the test reads that file rather than a
    copy of it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.integrations.didox.registry import (
    _LEGAL_FORM_ABBREVIATIONS,
    _LEGAL_FORM_KEYWORDS,
    normalize_legal_form,
)

_CONSTANTS = (
    Path(__file__).resolve().parents[2]
    / "portal"
    / "src"
    / "features"
    / "company-wizard"
    / "model"
    / "constants.ts"
)


def _select_options() -> list[str]:
    """The six codes the «Форма собственности» select offers, read from source.

    Parsed rather than duplicated: a second copy here would agree with the portal
    on the day it was written and silently stop agreeing later, which is exactly
    the failure the mapping exists to prevent.
    """
    src = _CONSTANTS.read_text(encoding="utf-8")
    match = re.search(r"export const LEGAL_FORMS = \[(.*?)\] as const;", src, re.S)
    assert match, f"LEGAL_FORMS not found in {_CONSTANTS}"
    return re.findall(r'"([^"]+)"', match.group(1))


class TestTheRegistryWordingBecomesACode:
    def test_the_captured_didox_record_maps_to_ooo(self) -> None:
        """The exact string in `tests/test_didox_client.py::INFO_FOUND`.

        It is abbreviated — «огр.», not «ограниченной» — so a mapping written
        against the spelt-out form alone passes its own tests and fails on the
        only real record we hold.
        """
        assert normalize_legal_form("Общество с огр. ответствен.") == "ООО"

    @pytest.mark.parametrize(
        "wording",
        [
            "Общество с ограниченной ответственностью",
            "ООО",
            "МЧЖ",
            "MCHJ",
            "Mas'uliyati cheklangan jamiyat",
            "МАСЪУЛИЯТИ ЧЕКЛАНГАН ЖАМИЯТ",
        ],
    )
    def test_every_spelling_of_an_llc_maps_to_ooo(self, wording: str) -> None:
        assert normalize_legal_form(wording) == "ООО"

    @pytest.mark.parametrize(
        ("wording", "expected"),
        [
            ("Акционерное общество", "АО"),
            ("Aksiyadorlik jamiyati", "АО"),
            ("Частное предприятие", "ЧП"),
            ("Xususiy korxona", "ЧП"),
            ("Совместное предприятие", "СП"),
            ("Qo'shma korxona", "СП"),
            ("Индивидуальный предприниматель", "ИП"),
            ("Yakka tartibdagi tadbirkor", "ИП"),
            ("Государственное унитарное предприятие", "ГУП"),
            ("Davlat unitar korxonasi", "ГУП"),
        ],
    )
    def test_the_other_five_forms(self, wording: str, expected: str) -> None:
        assert normalize_legal_form(wording) == expected

    def test_joint_stock_is_not_swallowed_by_the_llc_rule(self) -> None:
        """«Акционерное общество» contains «общество»; «Общество с огр…» is the
        LLC. Matching on the bare word would turn every JSC into an LLC."""
        assert normalize_legal_form("Акционерное общество") == "АО"

    def test_a_joint_venture_is_not_a_private_enterprise(self) -> None:
        """Three of the six end in «предприятие»; only the distinctive stem may
        decide which."""
        assert normalize_legal_form("Совместное предприятие") == "СП"
        assert normalize_legal_form("Частное предприятие") == "ЧП"


class TestItNeverInvents:
    def test_an_unrecognised_wording_is_returned_unchanged(self) -> None:
        """The portal offers it back as its own option. Guessing here would
        rewrite a real company's legal form into a neighbouring one."""
        assert normalize_legal_form("Простое товарищество") == "Простое товарищество"

    def test_a_pre_existing_free_text_value_survives(self) -> None:
        """`СП ООО` is in the seed data. It names two forms and belongs to
        neither cleanly, so it must reach the form intact rather than be
        collapsed into one of them."""
        assert normalize_legal_form("СП ООО") == "СП ООО"

    def test_nothing_in_means_nothing_out(self) -> None:
        assert normalize_legal_form(None) is None
        assert normalize_legal_form("") is None
        assert normalize_legal_form("   ") is None


class TestTheEndpointAppliesIt:
    """The mapper existing is not the fix — the prefill response carrying it is.

    Every test above passes with the normaliser written and never called, which
    is the shape this bug would come back in.
    """

    def test_the_prefill_response_carries_the_code_not_the_wording(self, monkeypatch) -> None:  # noqa: ANN001
        from app.domains.companies import lookup as lookup_service
        from app.domains.companies.api_portal import lookup_company
        from app.integrations.didox.client import DidoxCompanyInfo
        from tests.test_didox_client import INFO_FOUND

        info = DidoxCompanyInfo.from_payload(INFO_FOUND)
        assert info is not None
        assert info.legal_form == "Общество с огр. ответствен.", (
            "the fixture is the captured record; if Didox's wording changed here, "
            "the mapping below is being tested against something invented"
        )

        monkeypatch.setattr(lookup_service, "lookup_company", lambda *a, **k: info)

        class _Account:
            id = 1

        class _Redis:
            """Enough of the rate limiter's surface to get past its window."""

            def incr(self, key: str) -> int:
                return 1

            def expire(self, key: str, seconds: int) -> bool:
                return True

        out = lookup_company(
            tax_id="310529901",
            company_id=None,
            db=object(),  # type: ignore[arg-type]
            account=_Account(),  # type: ignore[arg-type]
            redis_client=_Redis(),  # type: ignore[arg-type]
        )

        assert out.found is True
        assert out.company is not None
        assert out.company.legal_form == "ООО", (
            "the select offers `ООО`; handing it the registry's wording makes it "
            "append a seventh option meaning the same thing"
        )
        # The rest of the record must be untouched by the mapping.
        assert out.company.short_name == '"DIDOX TECH" MCHJ'


class TestTheTargetsMatchTheSelect:
    def test_every_code_it_can_return_is_offered_by_the_select(self) -> None:
        """Otherwise the normalised value is itself unrecognised, the portal
        appends it as a seventh option, and the duplicate is back — now with our
        own spelling instead of the registry's."""
        offered = set(_select_options())
        produced = set(_LEGAL_FORM_ABBREVIATIONS.values()) | {
            code for _, code in _LEGAL_FORM_KEYWORDS
        }
        assert produced <= offered, (
            f"normalize_legal_form can return {sorted(produced - offered)}, which the "
            f"portal's LEGAL_FORMS does not offer ({sorted(offered)})"
        )

    def test_each_offered_code_normalises_to_itself(self) -> None:
        """A value already on the vocabulary must survive a round trip — the
        lookup runs on every ИНН keystroke, including re-edits of a saved row."""
        for code in _select_options():
            assert normalize_legal_form(code) == code
