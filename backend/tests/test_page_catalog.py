"""The page catalog agrees with the dashboard's navigation.

`app.core.pages.PAGES` is the vocabulary staff permissions are granted in, and
`dashboard/lib/nav.ts` is the list of screens people actually see — it backs both
the sidebar and the route guard. They are two files in two languages describing
one thing, so they can drift
— and each direction of drift is a real defect:

  * a nav item with no catalog entry is a page nobody can be granted, so it is
    administrator-only by accident and looks broken for everyone else;
  * a catalog entry with no nav item is a permission that grants nothing, which
    reads on the users screen as access the person does not have.

`adminUsers` is the one deliberate asymmetry — a nav item with no catalog entry,
because staff administration must not be grantable (see `app/api/admin_users.py`).
It is named here so that the exception is visible rather than absorbed.

Items and pages are no longer one-to-one. A `NavItem` may carry `page: "..."`
naming the permission it is granted by, and the seven Настройки проекта screens
all name `appSettings` — seven menu entries, one decision to delegate. So the
comparison below is on `page ?? key`, and the item→page direction is many-to-one:
what must hold is that every item resolves to a real page, and every page is
reachable from at least one item.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.pages import PAGES, is_page, satisfies

_NAV = Path(__file__).resolve().parents[2] / "dashboard" / "lib" / "nav.ts"

#: Nav items that must NOT be grantable. See the module docstring.
ADMIN_ONLY_NAV = frozenset({"adminUsers"})


def _nav() -> tuple[list[str], list[str]]:
    """(page keys the items resolve to, group keys) from the NAV_GROUPS block.

    An item is `key`, then `href`, then optionally `page` — the permission it is
    granted by when that is not its own key. The optional group is what makes
    several items able to share one grant.

    The field order is load-bearing: `key` must be immediately followed by
    `href`, and `page` must follow `href`. An item written any other way is
    invisible to this regex, and the failure surfaces as a confusing "PageSpec
    with no nav item" rather than as "your item is malformed".
    """
    src = _NAV.read_text(encoding="utf-8")
    block = src[src.index("const NAV_GROUPS") : src.index("export function pageForPath")]
    items = re.findall(
        r'\{\s*key: "(\w+)",\s*href: "[^"]*",(?:\s*page: "(\w+)",)?', block
    )
    return (
        [page or key for key, page in items],
        re.findall(r'\{\s*key: "(\w+)",\s*items:', block),
    )


@pytest.mark.skipif(not _NAV.exists(), reason="dashboard/ not checked out")
def test_every_nav_item_is_grantable_or_deliberately_admin_only() -> None:
    items, _ = _nav()
    assert items, "parsed no nav items — nav.ts changed shape, fix the parser"
    missing = [k for k in items if not is_page(k) and k not in ADMIN_ONLY_NAV]
    assert not missing, (
        f"nav items with no PageSpec: {missing}. They cannot be granted to anyone, "
        "so they are administrator-only by accident. Add them to app/core/pages.py "
        "or to ADMIN_ONLY_NAV here if that is deliberate."
    )


@pytest.mark.skipif(not _NAV.exists(), reason="dashboard/ not checked out")
def test_every_grantable_page_has_a_nav_item() -> None:
    items, _ = _nav()
    orphans = [p.key for p in PAGES if p.key not in items]
    assert not orphans, (
        f"PageSpecs with no nav item: {orphans}. Granting one would grant access "
        "to a screen that does not exist."
    )


@pytest.mark.skipif(not _NAV.exists(), reason="dashboard/ not checked out")
def test_page_groups_match_the_nav_groups() -> None:
    _, groups = _nav()
    unknown = sorted({p.group for p in PAGES} - set(groups))
    assert not unknown, (
        f"PageSpec groups absent from the nav: {unknown}. The users screen lays the "
        "matrix out by group, so a group the dashboard does not know cannot render."
    )


def test_admin_users_is_not_grantable() -> None:
    """Staff administration must never become a page an administrator can hand out.

    Whoever can edit staff accounts can mint an administrator or widen their own
    grants — so a grantable write here would be a privilege-escalation path that
    ends with someone holding every page nobody granted them.
    """
    assert not is_page("adminUsers")


def test_write_implies_read_but_not_the_reverse() -> None:
    assert satisfies("write", "read")
    assert satisfies("write", "write")
    assert satisfies("read", "read")
    assert not satisfies("read", "write")


def test_absence_is_denial() -> None:
    """No grant means no access — the property that makes a new page default-closed."""
    assert not satisfies(None, "read")
    assert not satisfies(None, "write")
