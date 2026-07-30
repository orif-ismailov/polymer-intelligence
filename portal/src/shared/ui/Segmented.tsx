import { cn } from "@/shared/lib";

export interface SegmentedOption {
  value: string;
  label: string;
}

interface SegmentedProps {
  options: readonly SegmentedOption[];
  value: string;
  onChange: (value: string) => void;
  /** Names the group for assistive tech — there is no visible legend. */
  ariaLabel: string;
  disabled?: boolean;
  className?: string;
  "data-testid"?: string;
}

/**
 * A pill-in-a-track toggle — «Образцы: Доступны / Не предоставляются» on the
 * sales-terms sheet.
 *
 * `role="radiogroup"` with real buttons rather than `Tabs`: tabs switch which
 * panel is *shown*, this switches what the offer *says*. Roving focus is left to
 * the browser (each button is tabbable) because the group never holds more than
 * three options — the arrow-key contract of a true radio group would cost more
 * than it buys here, and `aria-checked` still reads correctly.
 */
export function Segmented({
  options,
  value,
  onChange,
  ariaLabel,
  disabled,
  className,
  "data-testid": testId,
}: SegmentedProps) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex w-full gap-1 rounded-md border border-border bg-surface-inset p-1",
        className,
      )}
      data-testid={testId}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              "flex-1 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 focus-visible:ring-offset-bg",
              "disabled:pointer-events-none disabled:opacity-60",
              active
                ? "bg-brand text-brand-fg shadow-glow"
                : "text-text-muted hover:bg-surface-2 hover:text-text",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
