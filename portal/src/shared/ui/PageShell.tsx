import { type ReactNode } from "react";

import { cn, useTierBase } from "@/shared/lib";

export type PageWidth = "wide" | "default" | "narrow" | "storefront";

/**
 * The measure a page's content is held to.
 *
 * `AppShell`'s `<main>` already supplies the cabinet's outer container — 1600px
 * and the horizontal padding — so most pages need nothing and are wide by
 * default. This is the **opt-in narrower** wrapper for the ones that read
 * better in a column: wizards, message threads, settings.
 *
 * - `wide`     — no extra cap; fills the frame. Lists, tables, card grids.
 * - `default`  — 1152px. Detail pages that pair a body with a side rail.
 * - `narrow`   — 768px. Forms and threads, where a long line is a real cost.
 * - `storefront` — the both-tiers case, below.
 *
 * **`storefront`** is for the handful of pages mounted in the cabinet *and* on
 * the public site — the price table and the read-only directories. The public
 * shell provides no container of its own, so those pages carry their own; but
 * inside the cabinet that nested in `<main>`'s padding and pushed them 24px
 * right of every sibling page (and capped them at 1440 inside a column that was
 * 880). Now the container comes from whichever shell is actually rendering:
 * `<main>` in the cabinet, the page itself on the storefront. `useTierBase()`
 * is the mechanism already established for exactly this kind of tier
 * difference, so a new one is not invented here.
 */
interface PageShellProps {
  width?: PageWidth;
  className?: string;
  children: ReactNode;
}

const CAP: Record<Exclude<PageWidth, "storefront">, string> = {
  wide: "w-full",
  default: "mx-auto w-full max-w-6xl",
  narrow: "mx-auto w-full max-w-3xl",
};

export function PageShell({ width = "wide", className, children }: PageShellProps) {
  const inCabinet = useTierBase() !== "";
  const base =
    width === "storefront"
      ? // The storefront's own measure is deliberately 1440, not the cabinet's
        // 1600 — it is a different surface with a different rhythm, and this
        // change is not meant to move it.
        //
        // `mx-auto` is a no-op without a cap, and it is here so that a caller
        // tightening the measure through `className` (the company sheet wants
        // `max-w-6xl`) still centres in BOTH tiers rather than only on the
        // storefront.
        inCabinet
        ? "mx-auto w-full"
        : "mx-auto w-full max-w-[1440px] px-4 py-10 lg:px-6"
      : CAP[width];

  return <div className={cn(base, className)}>{children}</div>;
}
