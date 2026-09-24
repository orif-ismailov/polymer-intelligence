import { useRef } from "react";

import { cn } from "@/shared/lib";

interface ToggleChipsProps {
  /** Every choice, in display order. */
  options: readonly string[];
  value: readonly string[];
  onChange: (value: string[]) => void;
  /** Label for one option — a translated key, a code shown as-is, … */
  renderLabel: (option: string) => string;
  /** Single choice: selecting one clears the rest (and re-selecting clears it). */
  single?: boolean;
  /** Accessible name for the group. */
  label: string;
  className?: string;
  "data-testid"?: string;
}

/**
 * A wrap of pressable pills over a CLOSED set — processes, materials, languages.
 *
 * The wizard steps each carried their own copy of this (`aria-pressed` buttons
 * over a constants array); this is that pattern, once, for forms that need it
 * again. `ChipInput` is its free-text sibling.
 */
export function ToggleChips({
  options,
  value,
  onChange,
  renderLabel,
  single = false,
  label,
  className,
  "data-testid": testId,
}: ToggleChipsProps) {
  // The newest selection, including one emitted but not yet rendered back. Two
  // clicks inside one frame (fast taps, an autofill script) would otherwise both
  // compute from the same stale `value`, and the second would erase the first.
  const latest = useRef(value);
  latest.current = value;

  function toggle(option: string): void {
    const current = latest.current;
    const on = current.includes(option);
    const next = single
      ? on
        ? []
        : [option]
      : on
        ? current.filter((v) => v !== option)
        : [...current, option];
    latest.current = next;
    onChange(next);
  }

  return (
    <div role="group" aria-label={label} className={cn("flex flex-wrap gap-2", className)} data-testid={testId}>
      {options.map((option) => {
        const active = value.includes(option);
        return (
          <button
            key={option}
            type="button"
            aria-pressed={active}
            onClick={() => toggle(option)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-sm font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              active
                ? "border-brand bg-brand-soft text-text"
                : "border-border bg-surface text-text-muted hover:border-brand-line hover:text-text",
            )}
          >
            {renderLabel(option)}
          </button>
        );
      })}
    </div>
  );
}
