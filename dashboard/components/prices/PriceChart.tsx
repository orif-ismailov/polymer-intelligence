"use client";

/**
 * PriceChart — Recharts LineChart fed by GET /prices/series.
 *
 * Renders a ResponsiveContainer (100% x 400px) with multi-series lines
 * per product. Grid stroke uses border-subtle; axis labels use foreground-muted.
 *
 * SERIES_COLORS hex map: ONLY allowed hex in this file — Recharts stroke props
 * do not accept CSS variables (they render on SVG canvas). Values match
 * tailwind.config.ts token definitions exactly.
 */

import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { apiFetch } from "@/lib/api";

// ─── Series colors (ONLY allowed hex — Recharts stroke props require hex, not CSS vars)
// Values match tailwind.config.ts token definitions:
// accent = #10b981 (emerald-500), blue-500 = #3b82f6, violet-500 = #8b5cf6, amber-500 = #f59e0b
const SERIES_COLORS: Record<string, string> = {
  pp_raffia: "#10b981", // accent = emerald-500 (tailwind: accent.DEFAULT)
  hdpe: "#3b82f6",      // blue-500 (tailwind: kind.buy-request)
  ldpe: "#a78bfa",      // violet-400
  lldpe: "#34d399",     // emerald-400 (tailwind: accent.light)
  pvc: "#f59e0b",       // amber-500 (tailwind: urgency.medium)
  pet: "#8b5cf6",       // violet-500 (tailwind: kind.deal)
  ps: "#64748b",        // slate-500 (tailwind: foreground.subtle)
  abs: "#f97316",       // orange-500
};

const BORDER_SUBTLE = "#1e293b"; // tailwind: border.subtle (#1e293b = slate-800)
const AXIS_COLOR = "#94a3b8";    // tailwind: foreground.muted (#94a3b8 = slate-400)

// ─── Types ─────────────────────────────────────────────────────────────────────

interface PriceSeriesOut {
  observed_on: string;
  price_avg: number;
  currency: string;
}

interface PriceChartProps {
  product: string;         // product slug for label (pp_raffia, hdpe, etc.)
  market: string;          // UZEX, CBU, or empty for All
  dateFrom: string;        // ISO date string
  dateTo: string;          // ISO date string
  currency: "USD" | "UZS"; // display currency
  fxRate?: number;         // UZS per USD (for on-read conversion)
}

// ─── Slug → numeric product_id mapping ────────────────────────────────────────
// IDs match the seed data in seed_demo.py and the /prices/series backend contract.
// The backend only accepts product_id (integer); product_slug is a frontend concept.
const SLUG_TO_ID: Record<string, number> = {
  pp_raffia: 1,
  hdpe: 2,
  ldpe: 3,
  lldpe: 4,
  pvc: 5,
  pet: 6,
  ps: 7,
  abs: 8,
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ─── Main component ───────────────────────────────────────────────────────────

export function PriceChart({
  product,
  market,
  dateFrom,
  dateTo,
  currency,
  fxRate = 1,
}: PriceChartProps) {
  // Map slug → numeric product_id that the backend expects (CR-04).
  // product_slug is a frontend concept; the backend /prices/series only accepts product_id.
  const productId = SLUG_TO_ID[product];
  const params = new URLSearchParams({
    ...(productId != null ? { product_id: String(productId) } : {}),
    ...(market && market !== "All" ? { market } : {}),
    date_from: dateFrom,
    date_to: dateTo,
  });

  const { data = [], isLoading, error } = useQuery<PriceSeriesOut[]>({
    queryKey: ["prices", "series", product, market, dateFrom, dateTo],
    queryFn: () => apiFetch<PriceSeriesOut[]>(`/prices/series?${params.toString()}`),
  });

  // Apply FX conversion on read (price stored in original currency)
  const chartData = data.map((point) => ({
    date: point.observed_on,
    price: currency === "UZS" && point.currency === "USD"
      ? Number(point.price_avg) * fxRate
      : Number(point.price_avg),
    currency: point.currency,
  }));

  const strokeColor = SERIES_COLORS[product] ?? SERIES_COLORS.hdpe!;
  const yLabel = `${currency}/MT`;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[400px] bg-background-secondary rounded-lg border border-border">
        <div className="flex flex-col items-center gap-3">
          <div className="h-6 w-6 rounded-full border-2 border-accent border-t-transparent animate-spin" />
          <span className="text-sm text-foreground-muted">Loading price data…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-[400px] bg-background-secondary rounded-lg border border-urgency-high/30">
        <p className="text-sm text-urgency-high">Failed to load price data. Please refresh.</p>
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-[400px] bg-background-secondary rounded-lg border border-border">
        <p className="text-sm text-foreground-muted text-center max-w-xs">
          No price data for the selected filters. Adjust the date range or product selection.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full bg-background-secondary rounded-lg border border-border p-4">
      <ResponsiveContainer width="100%" height={400}>
        <LineChart
          data={chartData}
          margin={{ top: 8, right: 16, bottom: 8, left: 16 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            // SERIES_COLORS exception: border-subtle value (#1e293b = slate-800)
            stroke={BORDER_SUBTLE}
            strokeOpacity={1}
          />
          <XAxis
            dataKey="date"
            tickFormatter={formatDate}
            tick={{ fontSize: 12, fill: AXIS_COLOR }}
            axisLine={{ stroke: BORDER_SUBTLE }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 12, fill: AXIS_COLOR }}
            axisLine={{ stroke: BORDER_SUBTLE }}
            tickLine={false}
            label={{ value: yLabel, angle: -90, position: "insideLeft", fontSize: 11, fill: AXIS_COLOR }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1e293b", // bg-background-secondary
              border: "1px solid #334155", // border-DEFAULT
              borderRadius: "6px",
              fontSize: "12px",
              color: "#f8fafc", // foreground.DEFAULT
            }}
            formatter={(value: number) => [
              `${value.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${currency}/MT`,
              product.replace("_", " ").toUpperCase(),
            ]}
            labelFormatter={formatDate}
          />
          <Legend
            formatter={(value) => (
              <span style={{ fontSize: "12px", color: AXIS_COLOR }}>
                {value.replace("_", " ").toUpperCase()}
              </span>
            )}
          />
          <Line
            type="monotone"
            dataKey="price"
            name={product}
            // SERIES_COLORS exception: Recharts stroke prop cannot use CSS variables
            stroke={strokeColor}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: strokeColor }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
