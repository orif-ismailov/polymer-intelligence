import { cn } from "@/shared/lib";

export interface Step {
  id: number;
  label: string;
}

interface StepperProps {
  steps: readonly Step[];
  current: number;
  className?: string;
}

/** Horizontal numbered progress indicator for the company wizard. */
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
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-sm font-semibold",
                  isActive && "border-brand bg-brand text-brand-fg",
                  isDone && "border-brand bg-brand-soft text-brand",
                  !isActive && !isDone && "border-border bg-surface text-text-muted",
                )}
              >
                {isDone ? "✓" : step.id}
              </span>
              <span
                className={cn(
                  "hidden text-sm sm:inline",
                  isActive ? "font-medium text-text" : "text-text-muted",
                )}
              >
                {step.label}
              </span>
            </div>
            {index < steps.length - 1 ? (
              <span
                className={cn("mx-3 h-px flex-1", isDone ? "bg-brand" : "bg-border")}
                aria-hidden="true"
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
