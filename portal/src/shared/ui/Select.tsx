import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "@/shared/lib";

import { ChevronDownIcon } from "./icons";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  options: readonly SelectOption[];
  invalid?: boolean;
  placeholder?: string;
}

/**
 * The native control, wearing the mockups' chevron.
 *
 * `appearance-none` + our own glyph rather than the platform arrow: the UA arrow
 * is drawn from the system accent and, on a dark inset well, renders as a light
 * grey wedge that does not match the brand chevron used everywhere else.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { options, className, invalid, placeholder, ...rest },
  ref,
) {
  return (
    <div className="relative">
      <select
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(
          "h-10 w-full appearance-none rounded-md border bg-surface-inset px-3 pe-10 text-sm text-text",
          "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          "focus-visible:ring-offset-1 focus-visible:ring-offset-bg disabled:cursor-not-allowed disabled:opacity-60",
          invalid ? "border-danger" : "border-border",
          className,
        )}
        {...rest}
      >
        {placeholder !== undefined ? (
          <option value="" disabled>
            {placeholder}
          </option>
        ) : null}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <span className="pointer-events-none absolute inset-y-0 end-3 flex items-center text-text-muted">
        <ChevronDownIcon size={16} />
      </span>
    </div>
  );
});
