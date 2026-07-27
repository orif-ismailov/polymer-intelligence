import { useState } from "react";

import { Outlet } from "react-router-dom";

import { cn } from "@/shared/lib";

import { SideNav } from "./SideNav";
import { Topbar } from "./Topbar";

/**
 * Authenticated app layout: sticky topbar (with company switcher), a persistent
 * sidebar on desktop and a slide-over drawer on mobile, and the routed content.
 */
export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="min-h-screen bg-bg text-text">
      <Topbar onOpenMenu={() => setDrawerOpen(true)} />

      <div className="mx-auto flex max-w-5xl gap-8 px-4 py-6">
        <aside className="hidden w-52 shrink-0 md:block">
          <div className="sticky top-20">
            <SideNav />
          </div>
        </aside>

        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>

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
            className={cn(
              "absolute left-0 top-0 h-full w-64 border-r border-border bg-surface p-4 shadow-lg animate-fade-in",
            )}
          >
            <SideNav onNavigate={() => setDrawerOpen(false)} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
