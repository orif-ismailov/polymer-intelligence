import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/shared/lib";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

const inputBase =
  "h-10 w-full rounded-md border bg-surface px-3 text-sm text-text placeholder:text-text-subtle " +
  "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand " +
  "focus-visible:ring-offset-1 focus-visible:ring-offset-bg disabled:cursor-not-allowed disabled:opacity-60";

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(inputBase, invalid ? "border-danger" : "border-border", className)}
      {...rest}
    />
  );
});
