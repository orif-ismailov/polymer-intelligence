import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

interface FlowHeaderProps {
  /** Optically centred title. Rendered as the screen's `<h1>`. */
  title?: ReactNode;
  /** Left slot — the back chevron or a dismiss ✕. */
  leading?: ReactNode;
  /** Right slot — the language switcher on the entry sheet. */
  trailing?: ReactNode;
  className?: string;
}

/**
 * Header for a full-screen flow (registration): a glyph control on each side and
 * the title centred between them — distinct from {@link PageHeader}, which is the
 * left-aligned chrome of a cabinet page inside the app shell.
 *
 * The side slots are fixed-width rather than `justify-between`, so the title is
 * centred against the *screen* and does not shift when only one side has a
 * control. The `<h1>` is load-bearing: e2e flows locate screens by heading level.
 */
export function FlowHeader({ title, leading, trailing, className }: FlowHeaderProps) {
  return (
    <div
      className={cn("flex items-center gap-2", className)}
      data-testid="ui-flow-header"
    >
      <div className="flex w-9 shrink-0 justify-start">{leading}</div>
      {title ? (
        <h1 className="min-w-0 flex-1 truncate text-center text-base font-semibold text-text">
          {title}
        </h1>
      ) : (
        <div className="flex-1" />
      )}
      <div className="flex w-9 shrink-0 justify-end">{trailing}</div>
    </div>
  );
}
