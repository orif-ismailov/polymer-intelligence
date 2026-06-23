/**
 * Dashboard Home — KPI cards + Live Market Feed + AI Market Signals + Top panels.
 *
 * KPI cards (5): Total Buyers, Total Sellers, Active Requests, Hot Leads (D-01), Price Alerts.
 * Hot Leads renders in final layout with real count = requests WHERE lead_score IS NOT NULL
 * (0 in Phase 4 since Phase 5 fills lead_score). No hidden card per D-01.
 *
 * Live Market Feed panel: LiveFeedTable (compact).
 * AI Market Signals panel: AiMarketSignalsPanel (D-01 placeholder, final shape).
 *
 * "use client" required so Lucide icon components can be passed as props to KpiCard
 * (functions cannot be passed from Server Components to Client Components in Next.js).
 */

"use client";

import { Suspense } from "react";
import { Users, TrendingUp, FileText, Flame, Bell } from "lucide-react";

import { KpiCard } from "@/components/shared/KpiCard";
import { LiveFeedTable } from "@/components/feed/LiveFeedTable";
import { FeedFilters } from "@/components/feed/FeedFilters";
import { AiMarketSignalsPanel } from "@/components/feed/AiMarketSignalsPanel";

// Loading fallback for client components using useSearchParams
function FeedLoadingFallback() {
  return (
    <div className="flex items-center justify-center py-8">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      <span className="ml-3 text-sm text-foreground-muted">Loading…</span>
    </div>
  );
}

export default function DashboardHomePage() {
  return (
    <div className="p-8 space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold text-foreground">Dashboard</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Market overview and activity summary
        </p>
      </div>

      {/* KPI cards row — 5 cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {/* Total Buyers */}
        <KpiCard
          icon={Users}
          label="Total Buyers"
          value="—"
          delta={undefined}
        />
        {/* Total Sellers */}
        <KpiCard
          icon={TrendingUp}
          label="Total Sellers"
          value="—"
          delta={undefined}
        />
        {/* Active Requests */}
        <KpiCard
          icon={FileText}
          label="Active Requests"
          value="—"
          delta={undefined}
        />
        {/* Hot Leads — D-01: final layout, 0 in Phase 4 (lead_score filled in Phase 5) */}
        <KpiCard
          icon={Flame}
          label="Hot Leads"
          value={0}
          delta="high priority"
          deltaSentiment="neutral"
        />
        {/* Price Alerts */}
        <KpiCard
          icon={Bell}
          label="Price Alerts"
          value="—"
          delta={undefined}
        />
      </div>

      {/* Live Market Feed panel */}
      <div className="rounded-lg bg-background-secondary border border-border">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">Live Market Feed</h2>
          <a
            href="/signals"
            className="text-sm text-accent hover:text-accent-light transition-colors"
          >
            View all
          </a>
        </div>
        <div className="p-4">
          <Suspense fallback={null}>
            <FeedFilters compact className="mb-4" />
          </Suspense>
          <Suspense fallback={<FeedLoadingFallback />}>
            <LiveFeedTable compact />
          </Suspense>
        </div>
      </div>

      {/* Price Trends panel — placeholder (wired in 04-08) */}
      <div className="rounded-lg bg-background-secondary border border-border">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">Price Trends</h2>
          <a
            href="/prices"
            className="text-sm text-accent hover:text-accent-light transition-colors"
          >
            View all
          </a>
        </div>
        <div className="flex items-center justify-center py-12">
          <p className="text-sm text-foreground-subtle">
            Price trend chart — wired in Plan 04-08
          </p>
        </div>
      </div>

      {/* AI Market Signals panel — D-01: final layout, placeholder rows */}
      <AiMarketSignalsPanel />

      {/* Top Buyer Requests + Top Seller Offers panels */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-lg bg-background-secondary border border-border">
          <div className="border-b border-border px-6 py-4">
            <h2 className="text-base font-semibold text-foreground">Top Buyer Requests</h2>
          </div>
          <div className="flex items-center justify-center py-8">
            <p className="text-sm text-foreground-subtle">
              Wired in Plan 04-04 (Purchase Requests screen)
            </p>
          </div>
        </div>
        <div className="rounded-lg bg-background-secondary border border-border">
          <div className="border-b border-border px-6 py-4">
            <h2 className="text-base font-semibold text-foreground">Top Seller Offers</h2>
          </div>
          <div className="flex items-center justify-center py-8">
            <p className="text-sm text-foreground-subtle">
              Wired in Plan 04-05 (Offers screen)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
