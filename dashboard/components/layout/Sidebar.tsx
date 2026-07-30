"use client";

import { usePathname } from "@/i18n/navigation";
import { Link } from "@/i18n/navigation";
import { useState } from "react";
import {
  Activity,
  BadgeCheck,
  Banknote,
  FlaskConical,
  BarChart3,
  Bell,
  Boxes,
  Building2,
  Database,
  FileText,
  Flame,
  Globe,
  Handshake,
  Home,
  Inbox,
  LogOut,
  Microscope,
  Newspaper,
  Package,
  ShieldCheck,
  ShoppingCart,
  SlidersHorizontal,
  Tag,
  Users,
  Workflow,
  X,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface NavItem {
  /** Translation key under nav.items.* */
  key: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Role required to see this item. Undefined = visible to all roles. */
  minRole?: "admin" | "analyst" | "trader";
}

interface NavGroup {
  /** Translation key under nav.groups.* */
  key: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
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
      { key: "moderation", href: "/moderation", icon: ShieldCheck, minRole: "analyst" },
      { key: "offerRequests", href: "/offer-requests", icon: Inbox, minRole: "analyst" },
      { key: "verification", href: "/verification", icon: BadgeCheck, minRole: "analyst" },
      { key: "companies", href: "/companies", icon: Building2, minRole: "analyst" },
      { key: "contracts", href: "/contracts", icon: FileText, minRole: "analyst" },
      { key: "deals", href: "/deals", icon: Handshake, minRole: "analyst" },
      { key: "escrow", href: "/escrow", icon: Banknote, minRole: "analyst" },
      { key: "substances", href: "/substances", icon: FlaskConical, minRole: "analyst" },
      { key: "labOrders", href: "/lab-orders", icon: Microscope, minRole: "analyst" },
      { key: "labPartners", href: "/lab-partners", icon: Building2, minRole: "analyst" },
    ],
  },
  {
    key: "broker",
    items: [
      { key: "sourcing", href: "/sourcing", icon: Workflow, minRole: "analyst" },
      { key: "inventory", href: "/inventory", icon: Boxes, minRole: "analyst" },
      { key: "partners", href: "/partners", icon: Handshake, minRole: "analyst" },
      { key: "intel", href: "/intel", icon: BarChart3, minRole: "analyst" },
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
      { key: "reports", href: "/reports", icon: Newspaper, minRole: "analyst" },
      { key: "newsAdmin", href: "/admin/news", icon: SlidersHorizontal, minRole: "analyst" },
      { key: "prices", href: "/prices", icon: BarChart3 },
      {
        key: "adminProducts",
        href: "/admin/products",
        icon: Package,
        minRole: "admin",
      },
      {
        key: "adminUsers",
        href: "/admin/users",
        icon: Users,
        minRole: "admin",
      },
    ],
  },
];

/** Maps role string to numeric level for comparison */
const ROLE_LEVEL: Record<string, number> = {
  viewer: 0,
  trader: 1,
  analyst: 2,
  admin: 3,
};

const ROLE_MIN_LEVEL: Record<"admin" | "analyst" | "trader", number> = {
  trader: 1,
  analyst: 2,
  admin: 3,
};

function canView(item: NavItem, role: string | null): boolean {
  if (!item.minRole) return true;
  const userLevel = ROLE_LEVEL[role ?? "viewer"] ?? 0;
  return userLevel >= ROLE_MIN_LEVEL[item.minRole];
}

function getInitials(email: string): string {
  const parts = email.split("@")[0]?.split(".") ?? [];
  if (parts.length >= 2) {
    return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
  }
  return (email[0] ?? "?").toUpperCase();
}

const ROLE_BADGE_CLASSES: Record<string, string> = {
  admin: "bg-accent/20 text-accent",
  analyst: "bg-blue-500/20 text-blue-400",
  trader: "bg-amber-500/20 text-amber-400",
  viewer: "bg-background-tertiary text-foreground-muted",
};

interface SidebarProps {
  /** Mobile drawer state. Ignored at md+ where the sidebar is a static column. */
  open?: boolean;
  /** Close the mobile drawer (navigating, tapping ✕, or the scrim). */
  onClose?: () => void;
}

export function Sidebar({ open = false, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const t = useTranslations("nav");
  const [signingOut, setSigningOut] = useState(false);

  const role = user?.role ?? "viewer";

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  async function handleLogout() {
    setSigningOut(true);
    // logout() hard-navigates to /login, so there is no "finally" to run.
    await logout();
  }

  return (
    <aside
      id="dashboard-nav"
      className={cn(
        // Below md the sidebar is an off-canvas drawer: at 375px a fixed 240px
        // column left ~100px for the content and truncated every label into
        // fragments. At md+ it is the static column it has always been.
        "fixed inset-y-0 start-0 z-40 flex h-screen w-60 flex-shrink-0 flex-col",
        "bg-background-secondary border-e border-border transition-transform duration-200",
        "md:static md:z-auto",
        // The hidden state is scoped INSIDE `max-md:` rather than undone by a
        // `md:` counterpart: Tailwind emits `ltr:`/`rtl:` after the `md:` media
        // block, and `:where()` gives them equal specificity, so a bare
        // `ltr:-translate-x-full` would silently win at every width and slide the
        // desktop sidebar off-screen. `invisible` keeps it out of the tab order
        // while off-canvas, since a translated element is still focusable.
        !open && "max-md:invisible max-md:ltr:-translate-x-full max-md:rtl:translate-x-full",
      )}
      aria-label="Main navigation"
    >
      {/* Logo + wordmark */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-border">
        <Globe className="h-5 w-5 text-accent flex-shrink-0" aria-hidden="true" />
        <span className="text-base font-semibold text-accent leading-tight">
          Polymer Intelligence
        </span>
        <button
          type="button"
          onClick={onClose}
          className="ms-auto rounded-md p-1 text-foreground-muted hover:bg-background-tertiary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent md:hidden"
          aria-label={t("closeMenu")}
        >
          <X className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>

      {/* Nav groups */}
      <nav className="flex-1 overflow-y-auto py-4 px-3" aria-label="Dashboard navigation">
        {NAV_GROUPS.map((group) => {
          const visibleItems = group.items.filter((item) =>
            canView(item, role),
          );
          if (visibleItems.length === 0) return null;
          return (
            <div key={group.key} className="mb-6">
              {/* Group label */}
              <p className="mb-1 px-3 text-xs font-semibold uppercase tracking-wider text-foreground-muted">
                {t(`groups.${group.key}`)}
              </p>
              <ul role="list" className="space-y-0.5">
                {visibleItems.map((item) => {
                  const active = isActive(item.href);
                  const Icon = item.icon;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onClose}
                        className={cn(
                          "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-150",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                          active
                            ? "border-s-2 border-accent bg-background-tertiary text-foreground font-medium"
                            : "border-s-2 border-transparent text-foreground-muted hover:bg-background-tertiary hover:text-foreground",
                        )}
                        aria-current={active ? "page" : undefined}
                      >
                        <Icon
                          className={cn(
                            "h-4 w-4 flex-shrink-0",
                            active ? "text-accent" : "text-foreground-muted",
                          )}
                          aria-hidden="true"
                        />
                        {t(`items.${item.key}`)}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      {/* User footer */}
      <div className="border-t border-border px-4 py-4">
        <div className="mb-3">
          <LanguageSwitcher />
        </div>
        <div className="flex items-center gap-3">
          {/* Initials avatar */}
          <div
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-accent/20 text-accent text-xs font-semibold"
            aria-hidden="true"
          >
            {user ? getInitials(user.email) : (
              <Flame className="h-4 w-4" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-foreground">
              {user?.email ?? t("guest")}
            </p>
            <span
              className={cn(
                "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium",
                ROLE_BADGE_CLASSES[role] ?? ROLE_BADGE_CLASSES.viewer,
              )}
            >
              {role}
            </span>
          </div>
          {/* Sign out. Without this there was no way to end a session at all:
              the refresh cookie outlives the tab, so the next visit on a shared
              staff workstation silently resumed as whoever logged in last. */}
          <button
            type="button"
            onClick={handleLogout}
            disabled={signingOut}
            title={t("logout")}
            aria-label={t("logout")}
            className="flex-shrink-0 rounded-md p-2 text-foreground-muted transition-colors hover:bg-background-tertiary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>
  );
}
