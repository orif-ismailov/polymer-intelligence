import { cn } from "@/shared/lib";

export type TabsVariant = "underline" | "underlineGold" | "pill" | "segmented";

/*
 * A separate .ts sibling, like buttonStyles.ts: exporting a non-component
 * alongside a component from a .tsx file trips `react-refresh/only-export-components`,
 * which is a warning, which fails `eslint --max-warnings 0`.
 */

const base =
  "shrink-0 whitespace-nowrap transition-colors focus-visible:outline-none " +
  "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg";

const variants: Record<TabsVariant, { list: string; item: (active: boolean) => string }> = {
  /*
   * The mockups' section switcher (product detail, company profile, trade room).
   *
   * `min-w-0` matters: the strip scrolls horizontally, but a grid/flex item's
   * automatic minimum size is its content's min-content, so without this a row
   * of tabs silently widens its column past the viewport instead of scrolling.
   * A page that puts Tabs inside a grid column needs `min-w-0` on that column too.
   *
   * `overflow-y-hidden` alongside it is not decoration: setting only
   * `overflow-x` leaves `overflow-y`'s USED value as `auto` per the CSS
   * overflow spec (an axis left at `visible` while its sibling is not computes
   * to `auto`, not `visible`), so this row was a vertical scroller too — a
   * touch that started on the tab strip could drag the page instead of paging
   * through the tabs.
   */
  underline: {
    list: "flex min-w-0 max-w-full gap-2 overflow-x-auto overflow-y-hidden border-b border-border",
    item: (active) =>
      cn(
        "-mb-px rounded-t-sm border-b-2 px-3 py-2 text-sm",
        active
          ? "border-brand font-medium text-text"
          : "border-transparent text-text-muted hover:text-text",
      ),
  },
  /*
   * Product detail (`docs/new-design/product_detail.jpeg`): the active tab is
   * gold, not brand green — the sheet's secondary accent for section chrome.
   */
  underlineGold: {
    list: "flex min-w-0 max-w-full gap-2 overflow-x-auto overflow-y-hidden border-b border-border",
    item: (active) =>
      cn(
        "-mb-px rounded-t-sm border-b-2 px-3 py-2 text-sm",
        active
          ? "border-gold font-medium text-gold"
          : "border-transparent text-text-muted hover:text-text",
      ),
  },
  // The mockups' filter chips (market categories, deal scopes). Wraps rather
  // than scrolls, so it has no min-content problem.
  pill: {
    list: "flex min-w-0 flex-wrap items-center gap-2",
    item: (active) =>
      cn(
        "rounded-full border px-3 py-1.5 text-sm font-medium",
        active
          ? "border-brand-line bg-brand-soft text-brand"
          : "border-border text-text-muted hover:bg-surface-2 hover:text-text",
      ),
  },
  /*
   * The mockups' mode switcher inside a single well — E-IMZO «USB Token /
   * Mobile ID / Cloud ID». Unlike `pill`, the options share one bordered track
   * and split it evenly (`flex-1`), so the group reads as one control with a
   * selected segment rather than as three independent chips.
   */
  segmented: {
    list: "flex min-w-0 items-center gap-1 rounded-md border border-border bg-surface-inset p-1",
    item: (active) =>
      cn(
        "flex-1 rounded-sm px-3 py-2 text-center text-sm font-medium",
        active
          ? "bg-brand-soft text-brand shadow-glow"
          : "text-text-muted hover:bg-surface-2 hover:text-text",
      ),
  },
};

export function tabListClasses(variant: TabsVariant, className?: string): string {
  return cn(variants[variant].list, className);
}

export function tabItemClasses(variant: TabsVariant, active: boolean): string {
  return cn(base, variants[variant].item(active));
}
