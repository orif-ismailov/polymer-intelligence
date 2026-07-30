import { forwardRef, type ReactNode, type TextareaHTMLAttributes } from "react";

import { cn } from "@/shared/lib";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
  /** Glyph pinned to the right edge — see {@link import("./Input").InputProps.trailing}. */
  trailing?: ReactNode;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, invalid, trailing, rows = 4, ...rest },
  ref,
) {
  const field = (
    <textarea
      ref={ref}
      rows={rows}
      aria-invalid={invalid || undefined}
      className={cn(
        "w-full rounded-md border bg-surface-inset px-3 py-2 text-sm text-text placeholder:text-text-subtle",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        "focus-visible:ring-offset-1 focus-visible:ring-offset-bg disabled:cursor-not-allowed disabled:opacity-60",
        invalid ? "border-danger" : "border-border",
        // An adorned well pins its glyph to the top-right corner, which is
        // exactly where the drag grabber sits — the two overlap, so a field with
        // an adornment is fixed height by construction.
        trailing && "resize-none pe-11",
        className,
      )}
      {...rest}
    />
  );

  if (!trailing) return field;

  return (
    <div className="relative">
      {field}
      {/* Top-aligned: the mockup's address well is two lines tall and the pin
          sits beside the first, not floating in the vertical middle. */}
      <span className="pointer-events-none absolute end-3 top-2.5 flex items-center text-brand">
        {trailing}
      </span>
    </div>
  );
});
