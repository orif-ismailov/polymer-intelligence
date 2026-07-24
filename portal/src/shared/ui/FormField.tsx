import { type ReactNode, useId } from "react";

import { cn } from "@/shared/lib";

import { Label } from "./Label";

interface FormFieldProps {
  label?: string;
  required?: boolean;
  error?: string | null;
  hint?: string;
  className?: string;
  /** Render-prop receives the id to wire onto the control for a11y. */
  children: (fieldProps: { id: string; invalid: boolean; describedBy?: string }) => ReactNode;
}

/**
 * Layout + a11y wrapper for a labeled control. Wires label→control association
 * and surfaces error / hint text with `aria-describedby`.
 */
export function FormField({ label, required, error, hint, className, children }: FormFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const invalid = Boolean(error);
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cn("w-full", className)}>
      {label ? (
        <Label htmlFor={id} required={required}>
          {label}
        </Label>
      ) : null}
      {children({ id, invalid, describedBy })}
      {hint && !error ? (
        <p id={hintId} className="mt-1 text-xs text-text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="mt-1 text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
