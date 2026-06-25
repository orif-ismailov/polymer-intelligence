/**
 * Dashboard Home — KPI cards + Live Market Feed + Price Trends + AI Market Signals + Top panels.
 *
 * Data: GET /api/v1/dashboard/summary, fetched ONCE here via useDashboardSummary()
 * and sliced down to the panels (no double-fetching). Decimal fields arrive as JSON
 * strings — formatted at the display layer.
 *
 * KPI cards (5): Total Buyers, Total Sellers, Active Requests, Hot Leads, Price Alerts.
 * Live Market Feed: LiveFeedTable (compact) — wired already, left as-is.
 * Price Trends: PriceChart (PP Raffia / 30d / USD) with "View all → /prices" link.
 * AI Market Signals: AiMarketSignalsPanel fed real signals.
 * Top Buyer Requests / Top Seller Offers: compact lists fed from the summary.
 *
 * "use client" required so Lucide icon components can be passed as props to KpiCard
 * (functions cannot be passed from Server Components to Client Components in Next.js)
 * and so the page can fetch via react-query hooks.
 */

"use client";

import { Suspense } from "react";
import { Users, TrendingUp, FileText, Flame, Bell } from "lucide-react";

import { KpiCard } from "@/components/shared/KpiCard";
import { LiveFeedTable } from "@/components/feed/LiveFeedTable";
import { FeedFilters } from "@/components/feed/FeedFilters";
import { AiMarketSignalsPanel } from "@/components/feed/AiMarketSignalsPanel";
import { TopRequestsPanel } from "@/components/feed/TopRequestsPanel";
import { TopOffersPanel } from "@/components/feed/TopOffersPanel";
import { PriceChart } from "@/components/prices/PriceChart";
import { useDashboardSummary } from "@/hooks/useDashboardSummary";

// Loading fallback for client components using useSearchParams
function FeedLoadingFallback() {
  return (
    <div className="flex items-center justify-center py-8">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      <span className="ml-3 text-sm text-foreground-muted">Loading…</span>
    </div>
  );
}

// Default Price Trends chart selection: PP Raffia (product_id 1), last 30 days, USD.
const CHART_PRODUCT = "pp_raffia";
const CHART_DAYS = 30;

function toIsoDate(d: Date): string {
  return d.toISOString().split("T")[0]!;
}

function getChartRange(): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - CHART_DAYS);
  return { from: toIsoDate(from), to: toIsoDate(to) };
}

export default function DashboardHomePage() {
  const { data: summary, isLoading } = useDashboardSummary();
  const kpis = summary?.kpis;
  const chartRange = getChartRange();

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
        <KpiCard
          icon={Users}
          label="Total Buyers"
          value={kpis ? kpis.total_buyers : "—"}
        />
        <KpiCard
          icon={TrendingUp}
          label="Total Sellers"
          value={kpis ? kpis.total_sellers : "—"}
        />
        <KpiCard
          icon={FileText}
          label="Active Requests"
          value={kpis ? kpis.active_requests : "—"}
        />
        <KpiCard
          icon={Flame}
          label="Hot Leads"
          value={kpis ? kpis.hot_leads : "—"}
          delta="high priority"
          deltaSentiment="neutral"
        />
        <KpiCard
          icon={Bell}
          label="Price Alerts"
          value={kpis ? kpis.alert_rules : "—"}
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

      {/* Price Trends panel — PP Raffia / 30d / USD (PriceChart fetches its own series) */}
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
        <div className="p-4">
          <PriceChart
            product={CHART_PRODUCT}
            market="All"
            dateFrom={chartRange.from}
            dateTo={chartRange.to}
            currency="USD"
          />
        </div>
      </div>

      {/* AI Market Signals panel — real signals from the summary */}
      <AiMarketSignalsPanel signals={summary?.ai_signals} isLoading={isLoading} />

      {/* Top Buyer Requests + Top Seller Offers panels */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <TopRequestsPanel requests={summary?.top_requests} isLoading={isLoading} />
        <TopOffersPanel offers={summary?.top_offers} isLoading={isLoading} />
      </div>
    </div>
  );
}
