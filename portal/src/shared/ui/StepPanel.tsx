import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

import { Card } from "./Card";

interface StepPanelProps {
  /** The numeral in the tile. */
  step: number;
  title: string;
  /** Right-hand counter — «Шаг 3 из 7». Omitted on the closing sheets. */
  counter?: string;
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
}

/**
 * One sheet of the add-product flow: a numbered green tile, the sheet's title,
 * and the «Шаг N из 7» counter hard right, over a bordered body.
 *
 * The mockup draws all twelve sheets in this frame, which is why it is a
 * primitive and not a local component of the wizard — the request wizard and the
 * product page reuse the same header, and re-typing `h2 + text-sm + ml-auto` per
 * sheet is exactly how nine of them end up 2 px apart.
 */
export function StepPanel({
  step,
  title,
  counter,
  children,
  className,
  "data-testid": testId,
}: StepPanelProps) {
  return (
    <Card className={cn("overflow-hidden", className)} data-testid={testId}>
      <div className="flex items-center gap-3 border-b border-border bg-surface-2 px-4 py-3">
        <span className="num flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-brand text-sm font-bold text-brand-fg">
          {step}
        </span>
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold text-text">{title}</h2>
        {counter ? (
          <span className="num shrink-0 text-xs text-text-muted">{counter}</span>
        ) : null}
      </div>
      <div className="px-4 py-4">{children}</div>
    </Card>
  );
}
