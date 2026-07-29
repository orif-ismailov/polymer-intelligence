import { cn } from "@/shared/lib";

export type TabsVariant = "underline" | "pill";

/*
 * A separate .ts sibling, like buttonStyles.ts: exporting a non-component
 * alongside a component from a .tsx file trips `react-refresh/only-export-components`,
 * which is a warning, which fails `eslint --max-warnings 0`.
 */

const base =
  "shrink-0 whitespace-nowrap transition-colors focus-visible:outline-none " +
  "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg";

const variants: Record<TabsVariant, { list: string; item: (active: boolean) => string }> = {
  // The mockups' section switcher (product detail, company profile, trade room).
  underline: {
    list: "flex gap-2 overflow-x-auto border-b border-border",
    item: (active) =>
      cn(
        "-mb-px rounded-t-sm border-b-2 px-3 py-2 text-sm",
        active
          ? "border-brand font-medium text-text"
          : "border-transparent text-text-muted hover:text-text",
      ),
  },
  // The mockups' filter chips (market categories, deal scopes).
  pill: {
    list: "flex flex-wrap items-center gap-2",
    item: (active) =>
      cn(
        "rounded-full border px-3 py-1.5 text-sm font-medium",
        active
          ? "border-brand-line bg-brand-soft text-brand"
          : "border-border text-text-muted hover:bg-surface-2 hover:text-text",
      ),
  },
};

export function tabListClasses(variant: TabsVariant, className?: string): string {
  return cn(variants[variant].list, className);
}

export function tabItemClasses(variant: TabsVariant, active: boolean): string {
  return cn(base, variants[variant].item(active));
}
