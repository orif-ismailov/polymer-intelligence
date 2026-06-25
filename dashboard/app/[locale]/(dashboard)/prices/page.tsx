"use client";

/**
 * Price Trends page (/prices)
 *
 * Full-page LineChart with:
 * - Product pill tabs (PP Raffia / HDPE / LDPE / LLDPE / PVC / PET / PS / ABS)
 * - Market select (UZEX / CBU / All)
 * - Date-range presets 7d / 30d / 90d + custom start/end inputs
 * - Currency toggle USD/UZS (on-read FX conversion)
 *
 * No hardcoded hex. PriceChart uses SERIES_COLORS hex (Recharts exception).
 */

import { Suspense, useState } from "react";
import { TrendingUp } from "lucide-react";
import { PriceChart } from "@/components/prices/PriceChart";

// ─── Product config ────────────────────────────────────────────────────────────

const PRODUCTS = [
  { slug: "pp_raffia", label: "PP Raffia" },
  { slug: "hdpe", label: "HDPE" },
  { slug: "ldpe", label: "LDPE" },
  { slug: "lldpe", label: "LLDPE" },
  { slug: "pvc", label: "PVC" },
  { slug: "pet", label: "PET" },
  { slug: "ps", label: "PS" },
  { slug: "abs", label: "ABS" },
] as const;

type ProductSlug = typeof PRODUCTS[number]["slug"];

const MARKETS = ["UZEX", "CBU", "All"] as const;
type Market = typeof MARKETS[number];

type Currency = "USD" | "UZS";

// ─── Date presets ─────────────────────────────────────────────────────────────

function toIsoDate(d: Date): string {
  return d.toISOString().split("T")[0]!;
}

function getPreset(days: number): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - days);
  return { from: toIsoDate(from), to: toIsoDate(to) };
}

// ─── Main component ───────────────────────────────────────────────────────────

function PricesPageContent() {
  const [selectedProduct, setSelectedProduct] = useState<ProductSlug>("pp_raffia");
  const [market, setMarket] = useState<Market>("UZEX");
  const [currency, setCurrency] = useState<Currency>("USD");
  const [preset, setPreset] = useState<7 | 30 | 90 | null>(30);

  const defaultRange = getPreset(30);
  const [customFrom, setCustomFrom] = useState(defaultRange.from);
  const [customTo, setCustomTo] = useState(defaultRange.to);

  function handlePreset(days: 7 | 30 | 90) {
    setPreset(days);
    const range = getPreset(days);
    setCustomFrom(range.from);
    setCustomTo(range.to);
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <TrendingUp size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">Price Trends</h1>
          <p className="text-sm text-foreground-muted mt-0.5">
            Polymer market prices from UZEX and CBU
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Product pill tabs */}
        <div className="flex flex-wrap gap-2">
          {PRODUCTS.map((p) => (
            <button
              key={p.slug}
              onClick={() => setSelectedProduct(p.slug)}
              className={`rounded-full px-3 py-1.5 text-sm font-semibold border transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background ${
                selectedProduct === p.slug
                  ? "bg-accent text-white border-accent"
                  : "bg-background-secondary text-foreground-muted border-border hover:border-accent/50"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-4">
        {/* Market select */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-foreground-muted">Market</label>
          <select
            value={market}
            onChange={(e) => setMarket(e.target.value as Market)}
            className="rounded-md border border-border bg-background-secondary px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background"
          >
            {MARKETS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        {/* Date range presets */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-foreground-muted">Range</label>
          <div className="flex gap-1">
            {([7, 30, 90] as const).map((days) => (
              <button
                key={days}
                onClick={() => handlePreset(days)}
                className={`rounded-md px-3 py-2 text-sm font-medium border transition-colors ${
                  preset === days
                    ? "bg-accent text-white border-accent"
                    : "bg-background-secondary text-foreground-muted border-border hover:border-accent/50"
                }`}
              >
                {days}d
              </button>
            ))}
          </div>
        </div>

        {/* Custom date range */}
        <div className="flex items-end gap-2">
          <div className="flex flex-col gap-1">
            <label htmlFor="price-from" className="text-xs font-semibold text-foreground-muted">From</label>
            <input
              id="price-from"
              type="date"
              value={customFrom}
              onChange={(e) => { setCustomFrom(e.target.value); setPreset(null); }}
              className="rounded-md border border-border bg-background-secondary px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background"
            />
          </div>
          <span className="text-foreground-muted pb-2">–</span>
          <div className="flex flex-col gap-1">
            <label htmlFor="price-to" className="text-xs font-semibold text-foreground-muted">To</label>
            <input
              id="price-to"
              type="date"
              value={customTo}
              onChange={(e) => { setCustomTo(e.target.value); setPreset(null); }}
              className="rounded-md border border-border bg-background-secondary px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background"
            />
          </div>
        </div>

        {/* Currency toggle */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-foreground-muted">Currency</label>
          <div className="flex rounded-md border border-border overflow-hidden">
            {(["USD", "UZS"] as const).map((c) => (
              <button
                key={c}
                onClick={() => setCurrency(c)}
                className={`px-4 py-2 text-sm font-semibold transition-colors ${
                  currency === c
                    ? "bg-accent text-white"
                    : "bg-background-secondary text-foreground-muted hover:bg-background-tertiary"
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart */}
      <PriceChart
        product={selectedProduct}
        market={market}
        dateFrom={customFrom}
        dateTo={customTo}
        currency={currency}
      />
    </div>
  );
}

export default function PricesPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4 p-6">
          <div className="h-8 w-40 rounded bg-background-tertiary animate-pulse" />
          <div className="h-[400px] rounded bg-background-tertiary animate-pulse" />
        </div>
      }
    >
      <PricesPageContent />
    </Suspense>
  );
}
