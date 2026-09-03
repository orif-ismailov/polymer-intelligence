/**
 * The dashboard's navigation — and, with it, the vocabulary staff permissions
 * are granted in.
 *
 * SINGLE SOURCE OF TRUTH, on purpose. The Sidebar renders this list, the route
 * guard in the (dashboard) layout resolves a URL to a page key through it, and
 * `backend/app/core/pages.py` mirrors the same keys so an administrator can
 * grant them. `backend/tests/test_page_catalog.py` parses THIS FILE and fails if
 * the two drift — a nav item with no page cannot be granted to anyone, and a
 * page with no nav item grants access to a screen that does not exist.
 *
 * Adding a page means three edits: an entry here, a `PageSpec` in the backend
 * catalog, and a `require_page` on its endpoints. The first two are checked
 * against each other; the third is not, so an endpoint with no guard is still a
 * way in.
 */

import {
  Activity,
  BadgeCheck,
  Banknote,
  FlaskConical,
  BarChart3,
  Bell,
  Gauge,
  Boxes,
  Building2,
  Database,
  FileText,
  Handshake,
  Home,
  Inbox,
  Microscope,
  Newspaper,
  Package,
  ShieldCheck,
  ShoppingCart,
  SlidersHorizontal,
  Sparkles,
  Tag,
  TestTube,
  Truck,
  Users,
  Workflow,
} from "lucide-react";

export interface NavItem {
  /**
   * Translation key under nav.items.*, and — unless `page` says otherwise — the
   * page key this item is granted by. `app/core/pages.py` uses these exact
   * strings, and `backend/tests/test_page_catalog.py` fails if the two drift:
   * a nav item with no page cannot be granted to anyone, and a page with no nav
   * item grants access to a screen that does not exist.
   */
  key: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  /**
   * The page key this item is granted by, when that is NOT its own `key`.
   *
   * Exists because the sidebar and the permission model are allowed to disagree
   * about granularity. The seven Настройки проекта items are seven screens with
   * seven labels and seven URLs, but one decision to delegate: whoever may tune
   * the platform may tune all of it. Without this field `key` would have to be
   * both, so seven screens would mean seven grants — a permission matrix that
   * grew because a menu did.
   *
   * Read it as `item.page ?? item.key` everywhere. Three places do:
   * `Sidebar.tsx`, the `(dashboard)` route guard, and `StaffAccessMatrix.tsx` —
   * and the matrix must also DEDUPE on it, or several items render several
   * controls over one grant and the last click silently wins.
   *
   * Keep it after `href`: the catalog test's regex matches `key` immediately
   * followed by `href`, and an item it cannot see fails as a confusing orphan.
   */
  page?: string;
  /**
   * Visible only to administrators. Staff administration is deliberately NOT a
   * grantable page — whoever can edit staff accounts can mint an administrator.
   */
  adminOnly?: boolean;
}

/** The page key an item is granted by. */
export function pageKeyOf(item: NavItem): string {
  return item.page ?? item.key;
}


export interface NavGroup {
  /** Translation key under nav.groups.* */
  key: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    key: "main",
    items: [
      { key: "dashboard", href: "/", icon: Home },
      { key: "liveFeed", href: "/signals", icon: Activity },
    ],
  },
  {
    key: "requests",
    items: [
      { key: "purchaseRequests", href: "/requests", icon: ShoppingCart },
      { key: "offers", href: "/offers", icon: Tag },
      { key: "moderation", href: "/moderation", icon: ShieldCheck },
      { key: "offerRequests", href: "/offer-requests", icon: Inbox },
      { key: "verification", href: "/verification", icon: BadgeCheck },
      { key: "companies", href: "/companies", icon: Building2 },
      { key: "contracts", href: "/contracts", icon: FileText },
      { key: "deals", href: "/deals", icon: Handshake },
      { key: "escrow", href: "/escrow", icon: Banknote },
      { key: "substances", href: "/substances", icon: FlaskConical },
      { key: "labOrders", href: "/lab-orders", icon: Microscope },
      { key: "labPartners", href: "/lab-partners", icon: Building2 },
      { key: "logisticsRequests", href: "/logistics-requests", icon: Truck },
      { key: "labRequests", href: "/lab-requests", icon: TestTube },
    ],
  },
  {
    key: "broker",
    items: [
      { key: "sourcing", href: "/sourcing", icon: Workflow },
      { key: "inventory", href: "/inventory", icon: Boxes },
      { key: "partners", href: "/partners", icon: Handshake },
      { key: "intel", href: "/intel", icon: BarChart3 },
    ],
  },
  {
    key: "sources",
    items: [
      { key: "sources", href: "/sources", icon: Database },
      { key: "alerts", href: "/alerts", icon: Bell },
    ],
  },
  {
    key: "settings",
    items: [
      { key: "reports", href: "/reports", icon: Newspaper },
      { key: "newsAdmin", href: "/admin/news", icon: SlidersHorizontal },
      { key: "prices", href: "/prices", icon: BarChart3 },
      {
        key: "adminProducts",
        href: "/admin/products",
        icon: Package,
      },
      {
        key: "adminUsers",
        href: "/admin/users",
        icon: Users,
        adminOnly: true,
      },
    ],
  },
  // ── Настройки проекта ────────────────────────────────────────────────────
  // Seven screens, one grant. Each is a real route so it can be linked, opened
  // in a tab and found in history; `page: "appSettings"` is what stops seven
  // menu entries from becoming seven things an administrator has to tick.
  //
  // The settings themselves are grouped backend-side (`SettingSpec.group` in
  // `app/services/settings_service.py`) and each group maps to exactly one item
  // here — `test_settings_modules.py` fails if a group has no page, or a page no
  // settings, because either way somebody is looking at a menu that lies.
  {
    key: "projectSettings",
    items: [
      // NOT under /admin/settings/. `test_settings_modules.py` reads every
      // `/admin/settings/<module>` href out of this file and fails when one has
      // no matching `SettingSpec.group` — a menu entry leading to an empty page.
      // Analytics is a screen, not a group of switches, so it lives outside that
      // namespace and the invariant keeps meaning what it says. It shares the
      // group and the `appSettings` grant like everything else here.
      {
        key: "settingsAnalytics",
        href: "/admin/analytics",
        page: "appSettings",
        icon: Gauge,
      },
      {
        key: "settingsAi",
        href: "/admin/settings/ai",
        page: "appSettings",
        icon: Sparkles,
      },
      {
        key: "settingsNews",
        href: "/admin/settings/news",
        page: "appSettings",
        icon: Newspaper,
      },
      {
        key: "settingsNotifications",
        href: "/admin/settings/notifications",
        page: "appSettings",
        icon: Bell,
      },
      {
        key: "settingsDidox",
        href: "/admin/settings/didox",
        page: "appSettings",
        icon: FileText,
      },
      {
        key: "settingsDeals",
        href: "/admin/settings/deals",
        page: "appSettings",
        icon: Handshake,
      },
      {
        key: "settingsSourcing",
        href: "/admin/settings/sourcing",
        page: "appSettings",
        icon: Workflow,
      },
      {
        key: "settingsCompliance",
        href: "/admin/settings/compliance",
        page: "appSettings",
        icon: ShieldCheck,
      },
      {
        key: "settingsIngest",
        href: "/admin/settings/ingest",
        page: "appSettings",
        icon: Database,
      },
    ],
  },
];

/**
 * The settings modules, in sidebar order, derived from the nav rather than
 * listed again.
 *
 * The module is the last segment of each `/admin/settings/<module>` href, and it
 * is also the `SettingSpec.group` the backend stamps on every setting. Writing
 * that list twice is how a route ends up pointing at a group nothing belongs to
 * — so it is written once, above, and `test_settings_modules.py` checks this
 * file against the backend catalog in both directions.
 */
export const SETTINGS_MODULES: string[] = (
  NAV_GROUPS.find((g) => g.key === "projectSettings")?.items ?? []
)
  // Only the real settings routes. The group also holds Аналитика, which is a
  // screen rather than a group of switches and lives at `/admin/analytics`;
  // without this filter its last segment would be offered as a settings module
  // and `/admin/settings/analytics` would render an empty page instead of a 404.
  .filter((item) => item.href.startsWith("/admin/settings/"))
  .map((item) => item.href.split("/").pop() ?? "");

/**
 * The page key a dashboard path belongs to, or null for a path outside the nav.
 *
 * Longest-prefix wins so a detail route (`/companies/42`) resolves to its list
 * page. `/` is matched exactly — as a prefix it would swallow every route.
 */
export function pageForPath(pathname: string): NavItem | null {
  const items = NAV_GROUPS.flatMap((g) => g.items);
  if (pathname === "/") return items.find((i) => i.href === "/") ?? null;

  let best: NavItem | null = null;
  for (const item of items) {
    if (item.href === "/") continue;
    if (pathname === item.href || pathname.startsWith(item.href + "/")) {
      if (!best || item.href.length > best.href.length) best = item;
    }
  }
  return best;
}
