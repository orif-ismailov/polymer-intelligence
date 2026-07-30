import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { cn } from "@/shared/lib";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Accessible name — an icon-only control has no text to fall back on. */
  label: string;
  children: ReactNode;
}

/**
 * Bare glyph control for flow chrome: the mockups' back chevron, the dismiss ✕,
 * the language globe. Deliberately not a `Button` variant — those carry a height
 * and horizontal padding sized for a labelled action, which makes a 20 px glyph
 * sit in a box twice its size.
 */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, className, children, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-sm text-text transition-colors",
        "hover:bg-surface-2 hover:text-brand focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
        "disabled:pointer-events-none disabled:text-text-subtle",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
});
