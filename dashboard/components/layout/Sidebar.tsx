"use client";

import { usePathname } from "@/i18n/navigation";
import { Link } from "@/i18n/navigation";
import { useState } from "react";
import { Flame, Globe, LogOut, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { NAV_GROUPS, pageKeyOf } from "@/lib/nav";
import { LanguageSwitcher } from "./LanguageSwitcher";

function getInitials(email: string): string {
  const parts = email.split("@")[0]?.split(".") ?? [];
  if (parts.length >= 2) {
    return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
  }
  return (email[0] ?? "?").toUpperCase();
}

interface SidebarProps {
  /** Mobile drawer state. Ignored at md+ where the sidebar is a static column. */
  open?: boolean;
  /** Close the mobile drawer (navigating, tapping ✕, or the scrim). */
  onClose?: () => void;
}

export function Sidebar({ open = false, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { user, isAdmin, can, logout } = useAuth();
  const t = useTranslations("nav");
  const [signingOut, setSigningOut] = useState(false);

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
          // Hiding a link the user cannot use is a courtesy, not a permission —
          // the API refuses the request either way. A group whose every item is
          // hidden renders no heading, rather than an empty section.
          const visibleItems = group.items.filter((item) =>
            item.adminOnly ? isAdmin : can(pageKeyOf(item)),
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
            {user?.is_admin && (
              <span className="inline-flex items-center rounded bg-accent/20 px-1.5 py-0.5 text-xs font-medium text-accent">
                {t("adminBadge")}
              </span>
            )}
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
