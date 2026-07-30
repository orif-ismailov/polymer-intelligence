import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

interface StickyActionBarProps {
  children: ReactNode;
  className?: string;
}

/**
 * The mockups' phone action bar — "Написать продавцу · Запросить контракт ·
 * Escrow-платёж" pinned above the bottom navigation, so the primary actions of a
 * long detail screen are always in reach.
 *
 * `bottom-14` clears BottomNav's h-14 row (plus its safe-area padding). On desktop
 * it collapses to an ordinary row inside the flow, because there is no bottom bar
 * there and a floating strip would be noise.
 *
 * **A page that uses this must add `pb-36 md:pb-0`.** A fixed element does not
 * extend `<main>`'s box, so the bar will silently cover the last row of content —
 * and the e2e check that content clears the bottom nav cannot see it.
 */
export function StickyActionBar({ children, className }: StickyActionBarProps) {
  return (
    <div
      className={cn(
        "fixed inset-x-0 bottom-14 z-20 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur",
        "pb-[calc(0.75rem+env(safe-area-inset-bottom))]",
        "md:static md:z-auto md:border-0 md:bg-transparent md:p-0 md:backdrop-blur-none",
        className,
      )}
      data-testid="ui-sticky-action-bar"
    >
      <div className="mx-auto flex max-w-6xl items-center gap-2 md:mx-0 md:max-w-none">
        {children}
      </div>
    </div>
  );
}
