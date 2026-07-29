import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

import { CheckIcon } from "./icons";

export type StatusStepState = "done" | "current" | "pending";

export interface StatusStep {
  id: string;
  label: string;
  /** Timestamp or short explanation under the label. */
  hint?: string;
  state: StatusStepState;
  /** Trailing slot — a link, badge or action for this row. */
  action?: ReactNode;
}

interface StatusStepperProps {
  steps: readonly StatusStep[];
  className?: string;
}

/*
 * Mockup reading (contract signing / escrow / deal timeline): a completed row is
 * a filled green disc with a tick, the row in flight is a gold ring, and rows not
 * reached yet are hollow and muted. The connector inherits the *upper* row's
 * state so the green line grows downwards as the deal progresses.
 */
const marker: Record<StatusStepState, string> = {
  done: "border-brand bg-brand text-brand-fg",
  current: "border-gold bg-gold-soft text-gold",
  pending: "border-border bg-surface-inset text-text-subtle",
};

const labelTone: Record<StatusStepState, string> = {
  done: "text-text",
  current: "text-gold font-medium",
  pending: "text-text-muted",
};

/**
 * Vertical status timeline for a long-running process (contract signing, escrow,
 * the deal lifecycle). Purely presentational — the caller owns the state machine
 * and hands over already-resolved step states.
 */
export function StatusStepper({ steps, className }: StatusStepperProps) {
  return (
    <ol className={cn("space-y-0", className)}>
      {steps.map((step, index) => {
        const isLast = index === steps.length - 1;
        return (
          <li
            key={step.id}
            data-state={step.state}
            aria-current={step.state === "current" ? "step" : undefined}
            className="flex gap-3"
          >
            {/* Marker column: disc + connector down to the next row. */}
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border",
                  marker[step.state],
                )}
              >
                {step.state === "done" ? (
                  <CheckIcon size={13} />
                ) : (
                  <span
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      step.state === "current" ? "bg-gold" : "bg-text-subtle",
                    )}
                    aria-hidden="true"
                  />
                )}
              </span>
              {!isLast ? (
                <span
                  className={cn(
                    "my-1 w-px flex-1",
                    step.state === "done" ? "bg-brand-line" : "bg-border",
                  )}
                  aria-hidden="true"
                />
              ) : null}
            </div>

            <div className={cn("flex min-w-0 flex-1 items-start gap-3", isLast ? "pb-0" : "pb-4")}>
              <div className="min-w-0 flex-1">
                <p className={cn("text-sm", labelTone[step.state])}>{step.label}</p>
                {step.hint ? (
                  <p className="mt-0.5 text-xs text-text-muted num">{step.hint}</p>
                ) : null}
              </div>
              {step.action ? <div className="shrink-0">{step.action}</div> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
