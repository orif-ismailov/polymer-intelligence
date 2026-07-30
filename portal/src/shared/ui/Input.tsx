import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

import { cn } from "@/shared/lib";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  /**
   * Glyph or control pinned inside the right edge of the well. The registration
   * mockups adorn three fields this way (address → map pin, date → calendar,
   * PIN → reveal eye), so the affordance belongs to the primitive rather than
   * being re-wrapped in a `relative` div at each call site.
   */
  trailing?: ReactNode;
}

const inputBase =
  "h-10 w-full rounded-md border bg-surface-inset px-3 text-sm text-text placeholder:text-text-subtle " +
  "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand " +
  "focus-visible:ring-offset-1 focus-visible:ring-offset-bg disabled:cursor-not-allowed disabled:opacity-60";

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid, trailing, ...rest },
  ref,
) {
  const field = (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        inputBase,
        invalid ? "border-danger" : "border-border",
        // Reserve the adornment's column so a long value never runs under it.
        trailing && "pe-11",
        className,
      )}
      {...rest}
    />
  );

  if (!trailing) return field;

  return (
    <div className="relative">
      {field}
      <span className="pointer-events-none absolute inset-y-0 end-3 flex items-center text-brand [&_button]:pointer-events-auto">
        {trailing}
      </span>
    </div>
  );
});
