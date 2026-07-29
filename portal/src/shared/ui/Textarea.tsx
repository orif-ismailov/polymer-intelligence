import { forwardRef, type TextareaHTMLAttributes } from "react";

import { cn } from "@/shared/lib";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, invalid, rows = 4, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      rows={rows}
      aria-invalid={invalid || undefined}
      className={cn(
        "w-full rounded-md border bg-surface-inset px-3 py-2 text-sm text-text placeholder:text-text-subtle",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        "focus-visible:ring-offset-1 focus-visible:ring-offset-bg disabled:cursor-not-allowed disabled:opacity-60",
        invalid ? "border-danger" : "border-border",
        className,
      )}
      {...rest}
    />
  );
});
