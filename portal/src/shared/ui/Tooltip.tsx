import { type ReactNode, useId } from "react";

import { cn } from "@/shared/lib";

interface TooltipProps {
  content: string;
  children: ReactNode;
  className?: string;
}

/**
 * CSS-only hover/focus tooltip. Kept dependency-free — the trigger owns focus,
 * and the bubble is associated via `aria-describedby` for screen readers.
 */
export function Tooltip({ content, children, className }: TooltipProps) {
  const id = useId();
  return (
    <span className={cn("group relative inline-flex", className)}>
      <span aria-describedby={id}>{children}</span>
      <span
        role="tooltip"
        id={id}
        className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 -translate-x-1/2 whitespace-nowrap rounded-md bg-text px-2 py-1 text-xs text-bg opacity-0 shadow-md transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {content}
      </span>
    </span>
  );
}
