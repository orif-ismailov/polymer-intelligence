import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/shared/lib";

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
  description?: string;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, description, className, id, ...rest },
  ref,
) {
  return (
    <label
      htmlFor={id}
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-md border border-border bg-surface px-3 py-2.5 transition-colors hover:bg-surface-2 has-[:checked]:border-brand-line has-[:checked]:bg-brand-soft",
        className,
      )}
    >
      <input
        ref={ref}
        id={id}
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--brand)]"
        {...rest}
      />
      <span className="min-w-0">
        <span className="block text-sm font-medium text-text">{label}</span>
        {description ? <span className="mt-0.5 block text-xs text-text-muted">{description}</span> : null}
      </span>
    </label>
  );
});
