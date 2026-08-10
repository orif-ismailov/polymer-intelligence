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
 * `bottom-nav` clears the WHOLE of `BottomNav`, which is an `h-14` row **plus**
 * `pb-[env(safe-area-inset-bottom)]` — 90px on an iPhone with a home indicator,
 * not 56. This used to read `bottom-14`, the row's height alone, so on iOS the
 * bottom 34px of this bar sat behind the nav (`z-30` over this `z-20`) and the
 * cells' labels were sliced through the middle. Android and desktop report a
 * zero inset, which is why it only ever looked broken on a phone.
 *
 * The inset belongs to `bottom`, NOT to a `padding-bottom`, and that is load-
 * bearing: this component takes a `className`, and `OfferActionBar` passes
 * `!p-0` to make its three cells full-bleed. While the inset lived in the
 * padding, that one override silently deleted the whole correction — so the page
 * with the most crowded bar in the app was the one page with no compensation at
 * all. Position is ours; padding is the caller's.
 *
 * On desktop it collapses to an ordinary row inside the flow (`md:static` also
 * drops `bottom`), because there is no bottom bar there and a floating strip
 * would be noise.
 *
 * **A page that uses this must add `pb-action-bar md:pb-0`.** A fixed element
 * does not extend `<main>`'s box, so the bar will silently cover the last row of
 * content — and the e2e check that content clears the bottom nav cannot see it.
 */
export function StickyActionBar({ children, className }: StickyActionBarProps) {
  return (
    <div
      className={cn(
        "fixed inset-x-0 bottom-nav z-20 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur",
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
