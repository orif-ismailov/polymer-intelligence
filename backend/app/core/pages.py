"""
Dashboard page catalog — the vocabulary staff permissions are expressed in.

A staff account is granted access one PAGE at a time, at one of three levels:
no access, read, or write. This module is the closed set of pages that can be
granted, and every `require_page(...)` call names one of them.

Why pages rather than endpoints or domains. An administrator granting access is
thinking about the screens their colleague needs, not about the 111 routes
behind them or the 21 bounded contexts underneath. The dashboard's own
navigation is already that list, so the keys here are the `NavItem.key` values
from `dashboard/lib/nav.ts`, verbatim — the two must agree or a page appears in
the nav that no permission can grant.
`tests/test_page_catalog.py` reads that file and fails when they drift.

The levels are ordered: `write` implies `read`. There is no separate "no access"
value — a page a user holds no row for is a page they cannot reach, so a page
added to this catalog is closed to every non-administrator until somebody opens
it. Defaulting the other way would silently widen everyone's reach on deploy.

Administrators bypass the catalog entirely (`staff_users.is_admin`), which is
what keeps a new page reachable by somebody on the day it ships.

Adding a page means three edits: a `NavItem` in `dashboard/lib/nav.ts`, a
`PageSpec` here, and a `require_page` on its endpoints. The first two are checked
against each other; the third is not, so an endpoint with no guard is still a way in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: The two grantable levels. Absence of a grant is the third state.
AccessLevel = Literal["read", "write"]

#: Nav group keys, in the order the sidebar renders them. Used to lay the
#: permission matrix out the way the person granting access sees the product.
#:
#: These name bounded contexts. `requests` and `settings` are gone: the first had
#: become a 14-item catch-all holding the marketplace, the deal lifecycle,
#: compliance, labs and logistics, and the second held operational screens
#: (reports, news, prices) next to a group actually called project settings.
PageGroup = Literal[
    "main",
    "marketplace",
    "dealFlow",
    "counterparties",
    "labCompliance",
    "fulfilment",
    "broker",
    "content",
    "sources",
    "administration",
    "projectSettings",
]


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
    # ── marketplace ──────────────────────────────────────────────────────────
    PageSpec("purchaseRequests", "marketplace"),
    PageSpec("offers", "marketplace"),
    PageSpec("offerRequests", "marketplace"),
    PageSpec("moderation", "marketplace"),
    # ── dealFlow ─────────────────────────────────────────────────────────────
    PageSpec("contracts", "dealFlow"),
    PageSpec("deals", "dealFlow"),
    PageSpec("escrow", "dealFlow"),
    # ── counterparties ───────────────────────────────────────────────────────
    # `portalAccounts` belongs to this group in the nav but is NOT grantable —
    # see the note at the end of this tuple.
    PageSpec("companies", "counterparties"),
    PageSpec("verification", "counterparties"),
    PageSpec("technologists", "counterparties"),
    # ── labCompliance ────────────────────────────────────────────────────────
    PageSpec("labOrders", "labCompliance"),
    PageSpec("labPartners", "labCompliance"),
    PageSpec("substances", "labCompliance"),
    # ── fulfilment ───────────────────────────────────────────────────────────
    PageSpec("logisticsRequests", "fulfilment"),
    PageSpec("labRequests", "fulfilment"),
    # ── broker ───────────────────────────────────────────────────────────────
    PageSpec("sourcing", "broker"),
    PageSpec("inventory", "broker"),
    PageSpec("partners", "broker"),
    PageSpec("intel", "broker"),
    # ── content ──────────────────────────────────────────────────────────────
    PageSpec("newsAdmin", "content"),
    PageSpec("reports", "content"),
    PageSpec("prices", "content"),
    # ── sources ──────────────────────────────────────────────────────────────
    PageSpec("sources", "sources"),
    PageSpec("alerts", "sources"),
    # ── administration ───────────────────────────────────────────────────────
    # `adminUsers` is administrator-only and deliberately absent — see below.
    PageSpec("adminProducts", "administration"),
    PageSpec("adminBankRegister", "administration"),
    # ── projectSettings ──────────────────────────────────────────────────────
    # ONE grant behind NINE screens. The sidebar splits the settings by area so
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
    #
    # `portalAccounts` (0048) is absent for the same reason, one audience over:
    # whoever can issue a cabinet credential can sign in as a customer and act
    # inside their company — sign contracts, publish offers, read their deals.
    # That is authority being handed out, so it is `require_admin` too.
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
