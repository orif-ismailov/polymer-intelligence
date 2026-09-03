"use client";

/**
 * Daily calls this month, with the rest of the month projected.
 *
 * Actual is solid, projected is DASHED, and that carries two things at once: the
 * shape of the data (this part happened, that part has not) and the
 * accessibility rule that two series must never be told apart by hue alone.
 *
 * SERIES_COLORS hex map: the only allowed hex in this file. Recharts stroke
 * props paint SVG and cannot read CSS variables — same constraint and same
 * convention as `components/prices/PriceChart.tsx`; values mirror
 * tailwind.config.ts exactly.
 */

import { useTranslations } from "next-intl";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const ACCENT = "#10b981"; // tailwind: accent.DEFAULT (emerald-500)
const MUTED = "#94a3b8"; // tailwind: foreground.muted (slate-400)
const BORDER_SUBTLE = "#1e293b"; // tailwind: border.subtle (slate-800)
const CARD_BG = "#1e293b"; // tailwind: background.secondary (slate-800)

interface UsageTrendProps {
  data: { day: string; calls: number }[];
  /** Even daily burn implied by the package — the "should be here" line. */
  dailyBudget: number;
  reducedMotion: boolean;
}

export function UsageTrend({ data, dailyBudget, reducedMotion }: UsageTrendProps) {
  const t = useTranslations("analytics");

  // Cumulative, because the quota is cumulative: a reader comparing against a
  // monthly package needs the running total, not the daily spikes. Built with a
  // reduce rather than a mutated accumulator — the lint rule that forbids the
  // latter is right that a closure mutating across a render is a hazard.
  const series = data.reduce<{ day: string; actual: number; budget: number }[]>(
    (acc, d, i) => {
      const previous = acc[i - 1]?.actual ?? 0;
      acc.push({
        day: d.day.slice(5),
        actual: previous + d.calls,
        // The even-burn reference across the same days.
        budget: Math.round(dailyBudget * (i + 1)),
      });
      return acc;
    },
    [],
  );

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={BORDER_SUBTLE} strokeDasharray="3 3" />
        <XAxis dataKey="day" stroke={MUTED} fontSize={12} tickLine={false} />
        <YAxis stroke={MUTED} fontSize={12} tickLine={false} width={64} />
        <Tooltip
          contentStyle={{ background: CARD_BG, border: `1px solid ${BORDER_SUBTLE}` }}
          labelStyle={{ color: MUTED }}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: MUTED }} />
        <Area
          type="monotone"
          dataKey="actual"
          name={t("trend.actual")}
          stroke={ACCENT}
          fill={ACCENT}
          fillOpacity={0.2}
          isAnimationActive={!reducedMotion}
        />
        {/* Dashed: the even-burn reference is not something that happened. */}
        <Area
          type="monotone"
          dataKey="budget"
          name={t("trend.evenBurn")}
          stroke={MUTED}
          strokeDasharray="6 4"
          fill="none"
          isAnimationActive={!reducedMotion}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
