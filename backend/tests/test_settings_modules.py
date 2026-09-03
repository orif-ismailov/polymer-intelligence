"""
Every setting is reachable, and every settings screen has something on it.

`SettingSpec.group` used to be a heading on one long page, so a typo in it cost a
misplaced `<h2>`. Since the Настройки проекта split it is also a ROUTE — the
sidebar has one item per group at `/admin/settings/<group>` — which makes the
same typo mean a setting nobody can reach, on a page nobody can find, with
nothing anywhere saying so.

Two files describe that mapping (`app/services/settings_service.py` and
`dashboard/lib/nav.ts`) so it can drift, and each direction is a real defect:

  * a group with no nav item is a setting an operator cannot open, while
    `GET /admin/settings` cheerfully keeps returning it;
  * a nav item for a group with no settings is a menu entry leading to an empty
    page, which reads as a broken screen rather than as an empty one.

This is the same bargain `test_page_catalog.py` makes for pages, applied to the
level below it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services import settings_service

_NAV = Path(__file__).resolve().parents[2] / "dashboard" / "lib" / "nav.ts"

_requires_dashboard = pytest.mark.skipif(
    not _NAV.exists(), reason="dashboard/ not checked out"
)


def _nav_modules() -> list[str]:
    """The module segment of every `/admin/settings/<module>` href in the nav."""
    src = _NAV.read_text(encoding="utf-8")
    block = src[src.index("const NAV_GROUPS") : src.index("export function pageForPath")]
    return re.findall(r'href: "/admin/settings/(\w+)"', block)


def _spec_modules() -> set[str]:
    return {spec.group for spec in settings_service.SPECS.values()}


@_requires_dashboard
class TestEveryModuleIsReachable:
    def test_every_group_has_a_page(self) -> None:
        orphans = sorted(_spec_modules() - set(_nav_modules()))
        assert not orphans, (
            f"settings grouped under {orphans}, which no /admin/settings/<module> "
            "route serves — those settings cannot be opened by anyone"
        )

    def test_every_page_has_settings(self) -> None:
        empty = sorted(set(_nav_modules()) - _spec_modules())
        assert not empty, (
            f"nav items for {empty}, which no setting belongs to — a menu entry "
            "leading to an empty page reads as broken, not as empty"
        )

    def test_the_nav_lists_each_module_once(self) -> None:
        modules = _nav_modules()
        assert len(modules) == len(set(modules)), f"duplicate settings routes: {modules}"


class TestTheSplitLosesNothing:
    def test_every_setting_belongs_to_exactly_one_module(self) -> None:
        """The failure this restructure can produce: a setting that survives in
        `SPECS`, is returned by the API, and appears on no page because its group
        was renamed on one side of the filter only."""
        assert all(spec.group for spec in settings_service.SPECS.values())

    @_requires_dashboard
    def test_the_modules_account_for_every_setting(self) -> None:
        """Sum the pages; you must get the catalog back.

        Filtering thirty rows into seven buckets is exactly the operation that
        silently drops one, and a dropped setting is invisible: the page it left
        looks complete, and the page it should have joined never mentioned it.
        """
        modules = _nav_modules()
        counted = sum(
            1 for spec in settings_service.SPECS.values() if spec.group in modules
        )
        assert counted == len(settings_service.SPECS), (
            f"{len(settings_service.SPECS) - counted} setting(s) fall outside the "
            f"{len(modules)} module pages"
        )
