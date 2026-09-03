import { type CSSProperties, useState } from "react";

import { useTranslation } from "react-i18next";
import { Outlet } from "react-router-dom";

import { cn, RAIL_WIDTH, RAIL_WIDTH_COLLAPSED, useRailStore } from "@/shared/lib";
import { ChevronLeftIcon, ChevronRightIcon, IconButton } from "@/shared/ui";

import { MobileNav } from "./MobileNav";
import { SideNav } from "./SideNav";
import { Topbar } from "./Topbar";

/**
 * Authenticated app layout: a full-bleed topbar, a rail pinned to the viewport
 * edge on desktop, and on phones the mockups' bottom bar for the primary
 * destinations plus a slide-over drawer for the rest of the nav.
 *
 * **The frame is not a document.** It used to be one: chrome and content shared
 * a single `mx-auto max-w-6xl` container, so at a 1920 viewport `<main>` was
 * 880px with 384px of dead background on each side, the topbar's logo floated
 * 384px in from the corner it belongs in, and the rail — which had no
 * background and no border — read as loose links on the page rather than as a
 * surface. That is a reading measure (a prose container) applied to an
 * application, and it made the cabinet feel scoped rather than inhabited.
 *
 * So the two are separated. Chrome goes edge to edge; only `<main>` keeps a
 * measure, and a generous one (1600px) sized for tables and card grids rather
 * than for paragraphs. Pages that genuinely want a narrow column ask for it
 * themselves — see `shared/ui/PageShell`.
 *
 * The rail is `fixed` with the content wrapper reserving its width through
 * `padding-inline-start`, rather than a grid column. Two reasons: a fixed rail
 * gets its own scroll for free (`overflow-y-auto` on a full-height box), which
 * a sticky column inside a page-height row never had — the old one was only
 * ever reachable because the page happened to scroll far enough; and padding
 * animates everywhere, where `grid-template-columns` still does not.
 */
export function AppShell() {
  const { t } = useTranslation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const collapsed = useRailStore((s) => s.collapsed);
  const toggleRail = useRailStore((s) => s.toggle);

  return (
    <div
      className="min-h-screen bg-bg text-text"
      // The one number the rail and the content wrapper must agree on. Held in
      // a custom property so the two can never drift, and so the transition has
      // something to interpolate.
      style={{ "--rail-w": collapsed ? RAIL_WIDTH_COLLAPSED : RAIL_WIDTH } as CSSProperties}
    >
      <Topbar onOpenMenu={() => setDrawerOpen(true)} />

      {/* `top-14` is the topbar's `h-14`: the rail starts under it so the brand
          lockup keeps the actual corner. Opaque `bg-surface`, never
          `bg-surface/95` — a translucent panel is the silent light-theme
          failure `docs/design-system.md` warns about. */}
      <aside
        className={cn(
          "fixed bottom-0 start-0 top-14 z-20 hidden w-[var(--rail-w)] flex-col",
          "border-e border-border bg-surface md:flex",
          "motion-safe:transition-[width] motion-safe:duration-200",
        )}
      >
        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-4">
          <SideNav collapsed={collapsed} />
        </div>

        <div className="border-t border-border p-2">
          <IconButton
            label={t(collapsed ? "nav.expandRail" : "nav.collapseRail")}
            aria-expanded={!collapsed}
            onClick={toggleRail}
            className={cn("w-full", collapsed && "px-0")}
          >
            {/* The chevron points the way the rail is about to move. */}
            {collapsed ? <ChevronRightIcon /> : <ChevronLeftIcon />}
          </IconButton>
        </div>
      </aside>

      {/*
       * `pb-24` on phones keeps the last row clear of the fixed bottom bar — a
       * rule, not a preference: a fixed element does not extend the flow, and
       * `e2e/p0-ui-kit.spec.ts` asserts `main.bottom <= bottomNav.top`.
       *
       * It belongs on THIS wrapper and not on `<main>`. Padding is inside the
       * border box, so `pb-24` on `<main>` grows main's own rect by 96px and
       * pushes its bottom edge straight into the bar the padding was meant to
       * clear — the spec caught exactly that, 57px into the nav.
       */}
      <div className="pb-24 md:ps-[var(--rail-w)] md:pb-8 motion-safe:transition-[padding] motion-safe:duration-200">
        {/* `min-w-0` keeps the `Tabs` overflow chain intact for pages that put
            a tab strip in a grid column. */}
        <main className="mx-auto w-full min-w-0 max-w-[1600px] px-4 pt-6 lg:px-6 xl:px-8">
          <Outlet />
        </main>
      </div>

      <MobileNav />

      {/* Mobile drawer */}
      {drawerOpen ? (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-overlay animate-fade-in"
            onClick={() => setDrawerOpen(false)}
          />
          <div
            id="portal-nav-drawer"
            className={cn(
              "absolute start-0 top-0 h-full w-64 overflow-y-auto border-e border-border bg-surface p-4 shadow-lg animate-fade-in",
            )}
          >
            {/* Never collapsed, and on full 44px rows — this instance is only
                ever driven by a thumb. */}
            <SideNav touch onNavigate={() => setDrawerOpen(false)} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
