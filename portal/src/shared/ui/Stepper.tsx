import { cn } from "@/shared/lib";

import { CheckIcon } from "./icons";

export interface Step {
  id: number;
  label: string;
}

export type StepperVariant = "inline" | "stacked";

interface StepperProps {
  steps: readonly Step[];
  current: number;
  /**
   * `inline` puts the label beside the disc and hides it below `sm`.
   * `stacked` is the registration mockups' shape: label centred *under* every
   * disc, visible at 375 px, connectors running between the discs only.
   */
  variant?: StepperVariant;
  /**
   * Ids the user has actually finished. Omit it and "everything before `current`"
   * is assumed, which is only true when the flow can be entered at step 1 alone —
   * a URL-addressable wizard can be opened at step 4 with an empty draft, and the
   * rail then claimed three steps were done that the user had never seen.
   */
  completedIds?: readonly number[];
  className?: string;
}

/**
 * Horizontal numbered progress indicator (company wizard, RFQ wizard).
 *
 * Per the mockups: completed steps collapse to a green tick, the active step is
 * a filled green disc with a dark numeral, and upcoming steps stay hollow.
 */
export function Stepper({
  steps,
  current,
  variant = "inline",
  completedIds,
  className,
}: StepperProps) {
  const isComplete = (id: number): boolean =>
    completedIds ? completedIds.includes(id) : id < current;

  if (variant === "stacked") {
    return (
      <StackedStepper
        steps={steps}
        current={current}
        completedIds={completedIds}
        className={className}
      />
    );
  }

  return (
    <ol className={cn("flex w-full items-center", className)} aria-label="Progress">
      {steps.map((step, index) => {
        const isDone = isComplete(step.id);
        const isActive = step.id === current;
        return (
          <li key={step.id} className="flex flex-1 items-center last:flex-none">
            <div className="flex items-center gap-2">
              <Disc step={step} isDone={isDone} isActive={isActive} />
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

function Disc({ step, isDone, isActive }: { step: Step; isDone: boolean; isActive: boolean }) {
  return (
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
  );
}

/**
 * The connector has to run disc-to-disc, but each label is wider than its disc,
 * so the row is laid out as equal columns with the line drawn as an absolutely
 * positioned segment across the gap. Floating the line in normal flow (the
 * `inline` variant's trick) would push the labels apart instead.
 */
function StackedStepper({
  steps,
  current,
  completedIds,
  className,
}: Omit<StepperProps, "variant">) {
  const isComplete = (id: number): boolean =>
    completedIds ? completedIds.includes(id) : id < current;

  return (
    <ol className={cn("flex w-full items-start", className)} aria-label="Progress">
      {steps.map((step) => {
        const isDone = isComplete(step.id);
        const isActive = step.id === current;
        return (
          <li key={step.id} className="relative flex min-w-0 flex-1 flex-col items-center gap-1.5">
            {step.id > 1 ? (
              <span
                aria-hidden="true"
                className={cn(
                  // top-4 = the disc's vertical centre (h-8).
                  "absolute end-1/2 top-4 h-px w-full",
                  isDone || isActive ? "bg-brand" : "bg-border",
                )}
              />
            ) : null}
            <span className="relative z-10">
              <Disc step={step} isDone={isDone} isActive={isActive} />
            </span>
            {/* Wraps rather than truncates: five steps on a 375 px phone give
                each label ~65 px, and «Тип компании» clipped to «Тип комп…» is
                the one thing the rail exists to say. */}
            <span
              className={cn(
                "max-w-full text-balance px-0.5 text-center text-[10px] leading-tight",
                isActive ? "font-medium text-brand" : "text-text-muted",
              )}
            >
              {step.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
