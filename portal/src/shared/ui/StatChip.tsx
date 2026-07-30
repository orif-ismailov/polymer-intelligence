import { type HTMLAttributes, type ReactNode } from "react";

import { cn } from "@/shared/lib";

export type StatChipTone = "default" | "brand" | "gold";

interface StatChipProps extends Omit<HTMLAttributes<HTMLDivElement>, "children"> {
  /** The figure itself — pre-formatted by the caller ("50 000+", "98%"). */
  value: ReactNode;
  label: string;
  /** Optional delta / unit line under the label. */
  hint?: string;
  tone?: StatChipTone;
}

const valueTone: Record<StatChipTone, string> = {
  default: "text-text",
  brand: "text-brand",
  gold: "text-gold",
};

/**
 * Metric tile — the "50 000+ / Проверенных компаний" row on the mockup home
 * screen, and the counters on the company profile. Figures render tabular so a
 * row of chips doesn't shift as the numbers change.
 */
export function StatChip({
  value,
  label,
  hint,
  tone = "default",
  className,
  ...rest
}: StatChipProps) {
  return (
    <div className={cn("rounded-md border border-border bg-surface px-4 py-3", className)} {...rest}>
      <p
        data-testid="ui-stat-chip-value"
        className={cn("num text-xl font-semibold leading-tight", valueTone[tone])}
      >
        {value}
      </p>
      <p className="mt-0.5 text-xs text-text-muted">{label}</p>
      {hint ? <p className="mt-0.5 text-xs text-text-subtle num">{hint}</p> : null}
    </div>
  );
}
