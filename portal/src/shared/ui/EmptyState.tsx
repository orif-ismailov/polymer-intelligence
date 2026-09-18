import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
  className?: string;
  /**
   * Heading level for the title. `h3` by default, which is right for the 33
   * call sites that drop this block INSIDE a page that already has its own
   * `h1` — an empty table, a list with nothing in it yet.
   *
   * The 404 page is the case that is not that: there, the empty state IS the
   * page, and a document whose only heading is an `h3` has no title at all as
   * far as a screen reader's heading list is concerned (IMEX-20).
   */
  titleAs?: "h1" | "h2" | "h3";
}

export function EmptyState({
  title,
  description,
  action,
  icon,
  className,
  titleAs: Title = "h3",
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface px-6 py-12 text-center",
        className,
      )}
    >
      {icon ? <div className="mb-3 text-text-subtle">{icon}</div> : null}
      <Title className="text-base font-semibold text-text">{title}</Title>
      {description ? <p className="mt-1 max-w-sm text-sm text-text-muted">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
