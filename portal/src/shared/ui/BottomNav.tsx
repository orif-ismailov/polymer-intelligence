import { type ReactNode } from "react";

import { NavLink } from "react-router-dom";

import { cn } from "@/shared/lib";

export interface BottomNavItem {
  to: string;
  label: string;
  icon: ReactNode;
  /** Unread/pending count — rendered as the mockups' red pip. */
  badge?: number;
  /** Match nested routes too (e.g. `/market/42` keeps "Маркет" active). */
  end?: boolean;
}

interface BottomNavProps {
  items: readonly BottomNavItem[];
  className?: string;
}

/**
 * Mobile bottom navigation from the mockups (Главная · Заявки · Маркет · Сделки ·
 * Профиль). Phone-only — desktop keeps the sidebar, so this hides at `md`.
 *
 * The bar is fixed, so screens that use it must reserve space at the bottom
 * (`pb-20 md:pb-0`) or the last row of content hides behind it.
 */
export function BottomNav({ items, className }: BottomNavProps) {
  return (
    <nav
      data-testid="ui-bottom-nav"
      aria-label="Основная навигация"
      className={cn(
        "fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/95 backdrop-blur md:hidden",
        // Keep the row clear of the iOS home indicator.
        "pb-[env(safe-area-inset-bottom)]",
        className,
      )}
    >
      <ul className="flex items-stretch">
        {items.map((item) => (
          <li key={item.to} className="flex-1">
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "relative flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] transition-colors",
                  isActive ? "text-brand" : "text-text-muted",
                )
              }
            >
              <span className="relative">
                {item.icon}
                {item.badge ? (
                  <span
                    data-testid="ui-bottom-nav-badge"
                    className="num absolute -right-2 -top-1 min-w-4 rounded-full bg-danger px-1 text-[10px] font-semibold leading-4 text-danger-fg"
                  >
                    {item.badge}
                  </span>
                ) : null}
              </span>
              <span className="max-w-full truncate px-1">{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
