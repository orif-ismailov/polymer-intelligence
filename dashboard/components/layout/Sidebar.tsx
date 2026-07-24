"use client";

import { usePathname } from "@/i18n/navigation";
import { Link } from "@/i18n/navigation";
import {
  Activity,
  BadgeCheck,
  BarChart3,
  Bell,
  Boxes,
  Building2,
  Database,
  Flame,
  Globe,
  Handshake,
  Home,
  Inbox,
  Newspaper,
  Package,
  ShieldCheck,
  ShoppingCart,
  SlidersHorizontal,
  Tag,
  Users,
  Workflow,
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

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const t = useTranslations("nav");

  const role = user?.role ?? "viewer";

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <aside
      className="flex h-screen w-60 flex-shrink-0 flex-col bg-background-secondary border-e border-border"
      aria-label="Main navigation"
    >
      {/* Logo + wordmark */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-border">
        <Globe className="h-5 w-5 text-accent flex-shrink-0" aria-hidden="true" />
        <span className="text-base font-semibold text-accent leading-tight">
          Polymer Intelligence
        </span>
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
        </div>
      </div>
    </aside>
  );
}
