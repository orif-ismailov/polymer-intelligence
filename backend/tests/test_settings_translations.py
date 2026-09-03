"""
Every runtime switch is explained, in every language the dashboard ships.

The backend's `SettingSpec.label` is written for whoever maintains `Settings`:
"Escrow rail: stub (an operator confirms movement) or live (bank adapter)" tells
you the shape of the union, not what happens to money. The operator-facing name
and explanation live in `dashboard/messages/<locale>.json` under
`adminSettings.items.<key>`, because that is where next-intl reads translated
text from and where the other five locales already are.

Two places, so they can drift — which is the same hazard `test_page_catalog.py`
exists for, and the same remedy: a backend test that parses the frontend file.
Without it, adding a switch to `SPECS` silently ships a row labelled in English
with nothing under it, and nobody finds out until an operator is looking at a
setting they cannot interpret and does not touch.

The panel falls back to `spec.label` for a missing key, so a gap degrades to
English rather than to a raw message key. This test is what keeps that fallback
a safety net instead of somewhere strings quietly live.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import settings_service

_MESSAGES = Path(__file__).resolve().parents[2] / "dashboard" / "messages"

#: The locales `dashboard/CLAUDE.md` requires every string to exist in.
_LOCALES = ("ru", "uz", "tr", "fa", "zh")


def _doc(locale: str) -> dict[str, dict]:
    parsed: dict[str, dict] = json.loads(
        (_MESSAGES / f"{locale}.json").read_text(encoding="utf-8")
    )
    return parsed


def _items(locale: str) -> dict[str, dict[str, str]]:
    items: dict[str, dict[str, str]] = _doc(locale).get("adminSettings", {}).get("items", {})
    return items


def _groups(locale: str) -> dict[str, str]:
    groups: dict[str, str] = _doc(locale).get("adminSettings", {}).get("groups", {})
    return groups


@pytest.mark.parametrize("locale", _LOCALES)
class TestEverySwitchIsExplained:
    def test_no_switch_is_missing_a_translation(self, locale: str) -> None:
        missing = sorted(set(settings_service.SPECS) - set(_items(locale)))
        assert not missing, (
            f"{locale}.json has no adminSettings.items entry for: {', '.join(missing)}. "
            "A switch with no translation renders with its English developer label."
        )

    def test_every_entry_has_both_a_name_and_an_explanation(self, locale: str) -> None:
        """A name alone renames the problem; the explanation is the point."""
        for key, entry in _items(locale).items():
            assert entry.get("name", "").strip(), f"{locale}: {key} has no name"
            assert entry.get("desc", "").strip(), f"{locale}: {key} has no description"

    def test_no_translation_is_orphaned(self, locale: str) -> None:
        """A string for a key that no longer exists is dead weight that reads as
        coverage — the reverse drift, and the reason this check runs both ways."""
        orphans = sorted(set(_items(locale)) - set(settings_service.SPECS))
        assert not orphans, f"{locale}.json describes settings that do not exist: {orphans}"


@pytest.mark.parametrize("locale", _LOCALES)
class TestEveryModuleIsNamed:
    """The module label is the page's heading AND its sidebar item.

    An untranslated one is not a cosmetic gap here: with the settings split
    across seven screens, the label is the only thing on the page saying which
    area you are looking at.
    """

    def test_every_module_has_a_label(self, locale: str) -> None:
        modules = {spec.group for spec in settings_service.SPECS.values()}
        missing = sorted(modules - set(_groups(locale)))
        assert not missing, f"{locale}.json has no adminSettings.groups entry for: {missing}"

    def test_no_label_is_orphaned(self, locale: str) -> None:
        modules = {spec.group for spec in settings_service.SPECS.values()}
        orphans = sorted(set(_groups(locale)) - modules)
        assert not orphans, f"{locale}.json names settings groups that do not exist: {orphans}"


class TestTheLanguagesAgree:
    def test_all_locales_describe_the_same_settings(self) -> None:
        """One locale left behind is invisible to anyone who does not read it."""
        keys = {locale: set(_items(locale)) for locale in _LOCALES}
        reference = keys["ru"]
        for locale, found in keys.items():
            assert found == reference, (
                f"{locale}.json is out of step with ru.json: "
                f"missing {sorted(reference - found)}, extra {sorted(found - reference)}"
            )

    def test_the_text_is_actually_translated(self) -> None:
        """Copying the Russian into the other files would pass every check above.

        Not a quality judgement — just that somebody wrote something different,
        which is the cheapest available proof that a locale was not filled in by
        duplicating its neighbour.
        """
        ru = _items("ru")
        for locale in ("uz", "tr", "fa", "zh"):
            other = _items(locale)
            identical = [k for k in ru if other[k]["desc"] == ru[k]["desc"]]
            assert not identical, (
                f"{locale}.json repeats the Russian text verbatim for: {identical}"
            )
