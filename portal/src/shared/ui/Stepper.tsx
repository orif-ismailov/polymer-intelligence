import { cn } from "@/shared/lib";

import { CheckIcon } from "./icons";

export interface Step {
  id: number;
  label: string;
}

interface StepperProps {
  steps: readonly Step[];
  current: number;
  className?: string;
}

/**
 * Horizontal numbered progress indicator (company wizard, RFQ wizard).
 *
 * Per the mockups: completed steps collapse to a green tick, the active step is
 * a filled green disc with a dark numeral, and upcoming steps stay hollow. Step
 * labels hide below `sm` so the row still fits a 375 px phone.
 */
export function Stepper({ steps, current, className }: StepperProps) {
  return (
    <ol className={cn("flex w-full items-center", className)} aria-label="Progress">
      {steps.map((step, index) => {
        const isDone = step.id < current;
        const isActive = step.id === current;
        return (
          <li key={step.id} className="flex flex-1 items-center last:flex-none">
            <div className="flex items-center gap-2">
              <span
                aria-current={isActive ? "step" : undefined}
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-sm font-semibold transition-colors",
                  isActive && "border-brand bg-brand text-brand-fg shadow-glow",
                  isDone && "border-brand bg-brand-soft text-brand",
                  !isActive && !isDone && "border-border bg-surface text-text-subtle",
                )}
              >
                {isDone ? <CheckIcon size={16} /> : <span className="num">{step.id}</span>}
              </span>
              <span
                className={cn(
                  "hidden text-sm sm:inline",
                  isActive ? "font-medium text-brand" : "text-text-muted",
                )}
              >
                {step.label}
              </span>
            </div>
            {index < steps.length - 1 ? (
              <span
                className={cn("mx-2 h-px flex-1 sm:mx-3", isDone ? "bg-brand" : "bg-border")}
                aria-hidden="true"
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
