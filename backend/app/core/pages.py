"""
Dashboard page catalog — the vocabulary staff permissions are expressed in.

A staff account is granted access one PAGE at a time, at one of three levels:
no access, read, or write. This module is the closed set of pages that can be
granted, and every `require_page(...)` call names one of them.

Why pages rather than endpoints or domains. An administrator granting access is
thinking about the screens their colleague needs, not about the 111 routes
behind them or the 21 bounded contexts underneath. The dashboard's own
navigation is already that list, so the keys here are the `NavItem.key` values
from `dashboard/components/layout/Sidebar.tsx`, verbatim — the two must agree or
a page appears in the nav that no permission can grant.
`tests/test_page_catalog.py` reads the Sidebar and fails when they drift.

The levels are ordered: `write` implies `read`. There is no separate "no access"
value — a page a user holds no row for is a page they cannot reach, so a page
added to this catalog is closed to every non-administrator until somebody opens
it. Defaulting the other way would silently widen everyone's reach on deploy.

Administrators bypass the catalog entirely (`staff_users.is_admin`), which is
what keeps a new page reachable by somebody on the day it ships.

Adding a page means three edits: a `NavItem` in the Sidebar, a `PageSpec` here,
and a `require_page` on its endpoints. The first two are checked against each
other; the third is not, so an endpoint with no guard is still a way in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: The two grantable levels. Absence of a grant is the third state.
AccessLevel = Literal["read", "write"]

#: Nav group keys, in the order the sidebar renders them. Used to lay the
#: permission matrix out the way the person granting access sees the product.
PageGroup = Literal["main", "requests", "broker", "sources", "settings", "projectSettings"]


@dataclass(frozen=True)
class PageSpec:
    """One grantable dashboard page.

    `key` matches the dashboard `NavItem.key`; `group` matches its `NavGroup.key`.
    Neither carries a label — the dashboard already translates these keys into
    five languages under `nav.*`, and a second copy here would be the one that
    goes stale.
    """

    key: str
    group: PageGroup


PAGES: tuple[PageSpec, ...] = (
    # ── main ─────────────────────────────────────────────────────────────────
    PageSpec("dashboard", "main"),
    PageSpec("liveFeed", "main"),
    # ── requests ─────────────────────────────────────────────────────────────
    PageSpec("purchaseRequests", "requests"),
    PageSpec("offers", "requests"),
    PageSpec("moderation", "requests"),
    PageSpec("offerRequests", "requests"),
    PageSpec("verification", "requests"),
    PageSpec("companies", "requests"),
    PageSpec("contracts", "requests"),
    PageSpec("deals", "requests"),
    PageSpec("escrow", "requests"),
    PageSpec("substances", "requests"),
    PageSpec("labOrders", "requests"),
    PageSpec("labPartners", "requests"),
    PageSpec("logisticsRequests", "requests"),
    PageSpec("labRequests", "requests"),
    # ── broker ───────────────────────────────────────────────────────────────
    PageSpec("sourcing", "broker"),
    PageSpec("inventory", "broker"),
    PageSpec("partners", "broker"),
    PageSpec("intel", "broker"),
    # ── sources ──────────────────────────────────────────────────────────────
    PageSpec("sources", "sources"),
    PageSpec("alerts", "sources"),
    # ── settings ─────────────────────────────────────────────────────────────
    PageSpec("reports", "settings"),
    PageSpec("newsAdmin", "settings"),
    PageSpec("prices", "settings"),
    PageSpec("adminProducts", "settings"),
    # ── projectSettings ──────────────────────────────────────────────────────
    # ONE grant behind SEVEN screens. The sidebar splits the settings by area so
    # an operator can find one; the permission does not follow that split,
    # because "may tune the platform" is a single decision to delegate and a
    # seven-row matrix would only make it look like seven.
    #
    # The nav items carry `page: "appSettings"` (see `dashboard/lib/nav.ts`) and
    # `StaffAccessMatrix` dedupes on it, so this stays one row.
    #
    # Grantable, but with a second gate inside the router: the two Didox
    # CREDENTIALS additionally require `is_admin`, whatever this grant says.
    # A page grant is the right shape for "let the ops lead retune the news
    # cadence"; handing over a partner token is not the same act, and the
    # difference has to be visible somewhere other than a reviewer's memory.
    PageSpec("appSettings", "projectSettings"),
    # NOTE: `adminUsers` is deliberately NOT here. Staff administration is
    # administrator-only (`require_admin`), because a grantable write on it is a
    # privilege-escalation path: whoever can edit staff accounts can mint an
    # administrator, or widen their own grants, and would then hold every page
    # without anyone having granted them one. Nothing that can hand out
    # authority may itself be handed out.
)

PAGE_KEYS: frozenset[str] = frozenset(p.key for p in PAGES)


def is_page(key: str) -> bool:
    """Whether `key` names a page in the catalog.

    Granting an unknown page is rejected rather than stored: a row nothing ever
    checks grants nothing, and it would read on the users screen as access the
    person does not have.
    """
    return key in PAGE_KEYS


def satisfies(granted: str | None, required: AccessLevel) -> bool:
    """Whether a stored grant meets a required level.

    `write` implies `read` — the alternative is granting both on every page that
    needs editing, which is a checkbox users would forget and a permission bug
    that reads as a broken screen.
    """
    if granted is None:
        return False
    if granted == "write":
        return True
    return required == "read"
