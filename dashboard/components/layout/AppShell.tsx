"use client";

import { useState } from "react";
import { Menu } from "lucide-react";
import { useTranslations } from "next-intl";
import { Sidebar } from "@/components/layout/Sidebar";
import { SessionWatcher } from "@/components/layout/SessionWatcher";

interface AppShellProps {
  children: React.ReactNode;
}

/**
 * AppShell — 240px sidebar + scrollable main content area.
 *
 * At md+ the sidebar is a static column (RESEARCH.md Recommended Project Structure).
 * Below md it becomes an off-canvas drawer opened from a top bar: a fixed column at
 * 375px left roughly 100px of usable width and truncated every label into fragments.
 */
export function AppShell({ children }: AppShellProps) {
  const t = useTranslations("nav");
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />

      {/* Scrim — mobile only, and only while the drawer is open. */}
      {navOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
          onClick={() => setNavOpen(false)}
          aria-hidden="true"
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* The only route to navigation below md — the sidebar is off-canvas there. */}
        <header className="flex items-center gap-3 border-b border-border bg-background-secondary px-4 py-3 md:hidden">
          <button
            type="button"
            onClick={() => setNavOpen(true)}
            aria-label={t("openMenu")}
            aria-expanded={navOpen}
            aria-controls="dashboard-nav"
            className="rounded-md p-1 text-foreground-muted transition-colors hover:bg-background-tertiary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
          <span className="truncate text-sm font-semibold text-accent">
            Polymer Intelligence
          </span>
        </header>

        <main className="flex-1 overflow-y-auto" id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>

      <SessionWatcher />
    </div>
  );
}
