"use client";

/**
 * AiMarketSignalsPanel — D-01 placeholder-aware AI panel.
 * Final layout shape with 3 placeholder rows — NOT a blank card, NOT a spinner.
 * Each row: icon + "AI analysis available after Phase 5" text + time placeholder.
 * Phase 5 wires in real AI signal data here.
 *
 * D-01 contract: "No hidden sections and no dead-end blank cards — Phase 5 just fills the data."
 */

import { Bot, TrendingUp, AlertTriangle } from "lucide-react";

const PLACEHOLDER_ROWS = [
  {
    icon: TrendingUp,
    label: "Market trend analysis",
  },
  {
    icon: AlertTriangle,
    label: "Demand signal detection",
  },
  {
    icon: Bot,
    label: "Price movement insight",
  },
];

interface AiMarketSignalsPanelProps {
  className?: string;
}

export function AiMarketSignalsPanel({ className = "" }: AiMarketSignalsPanelProps) {
  return (
    <div
      className={`rounded-lg bg-background-secondary border border-border ${className}`}
      aria-label="AI Market Signals panel"
    >
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-2">
          <Bot size={20} className="text-foreground-muted" aria-hidden="true" />
          <h2 className="text-base font-semibold text-foreground">AI Market Signals</h2>
        </div>
        <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-semibold text-amber-400 border border-amber-500/30">
          after Phase 5
        </span>
      </div>
      <div className="divide-y divide-border">
        {PLACEHOLDER_ROWS.map((row, i) => {
          const Icon = row.icon;
          return (
            <div
              key={i}
              className="flex items-start gap-3 px-6 py-4"
            >
              <Icon
                size={20}
                className="mt-0.5 flex-shrink-0 text-foreground-muted"
                aria-hidden="true"
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-foreground-subtle italic">
                  {row.label} — AI analysis available after Phase 5
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
