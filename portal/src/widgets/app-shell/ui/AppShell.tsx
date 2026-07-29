import { useState } from "react";

import { Outlet } from "react-router-dom";

import { cn } from "@/shared/lib";

import { MobileNav } from "./MobileNav";
import { SideNav } from "./SideNav";
import { Topbar } from "./Topbar";

/**
 * Authenticated app layout: sticky topbar (with company switcher), a persistent
 * sidebar on desktop, and on phones the mockups' bottom bar for the primary
 * destinations plus a slide-over drawer for the rest of the nav.
 */
export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="min-h-screen bg-bg text-text">
      <Topbar onOpenMenu={() => setDrawerOpen(true)} />

      {/* `pb-24` on phones keeps the last row clear of the fixed bottom bar. */}
      <div className="mx-auto flex max-w-6xl gap-8 px-4 pb-24 pt-6 md:pb-6">
        <aside className="hidden w-52 shrink-0 md:block">
          <div className="sticky top-20">
            <SideNav />
          </div>
        </aside>

        <main className="min-w-0 flex-1">
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
              "absolute start-0 top-0 h-full w-64 border-e border-border bg-surface p-4 shadow-lg animate-fade-in",
            )}
          >
            <SideNav onNavigate={() => setDrawerOpen(false)} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
