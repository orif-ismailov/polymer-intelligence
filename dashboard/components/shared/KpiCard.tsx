"use client";

/**
 * KpiCard — KPI metric card.
 * Anatomy: icon (24px, foreground-muted) + label (12px/600, foreground-muted) + value (28px/600) + optional delta chip.
 * UI-SPEC §Dashboard Home KPI cards.
 * No hardcoded hex — token classes only.
 */

import type { LucideIcon } from "lucide-react";

interface KpiCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  /** Optional delta text, e.g. "+24 today" */
  delta?: string;
  /** Delta sentiment — "positive" uses accent, "neutral" uses status-new blue, "negative" uses urgency-high */
  deltaSentiment?: "positive" | "neutral" | "negative";
  className?: string;
}

const DELTA_CLASSES = {
  positive: "text-accent",
  neutral: "text-status-new",
  negative: "text-urgency-high",
};

export function KpiCard({
  icon: Icon,
  label,
  value,
  delta,
  deltaSentiment = "neutral",
  className = "",
}: KpiCardProps) {
  const deltaClass = DELTA_CLASSES[deltaSentiment];

  return (
    <div
      className={`rounded-lg bg-background-secondary border border-border p-6 flex flex-col gap-2 ${className}`}
    >
      <div className="flex items-center gap-2">
        <Icon size={24} className="text-foreground-muted flex-shrink-0" aria-hidden="true" />
        <span className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
          {label}
        </span>
      </div>
      <div className="flex items-end gap-3">
        <span className="text-[28px] font-semibold text-foreground leading-none">
          {value}
        </span>
        {delta && (
          <span className={`text-xs font-semibold ${deltaClass} pb-0.5`}>
            {delta}
          </span>
        )}
      </div>
    </div>
  );
}
