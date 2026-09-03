"use client";

/**
 * What a panel shows when there is nothing to show.
 *
 * The reason this exists rather than rendering the zeros: a fresh deployment and
 * a broken one produce the same 0, and "we spent nothing" and "nothing has run
 * yet" are opposite facts wearing the same digit. A reader who sees 0 calls next
 * to a million-request quota concludes the integration is idle, which may be
 * exactly wrong.
 *
 * So every block on this page carries `has_data` from the API and renders this
 * instead — a sentence saying which of the two it is.
 *
 * No hardcoded hex — token classes only.
 */

import type { LucideIcon } from "lucide-react";

export function EmptyPanel({
  icon: Icon,
  title,
  hint,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-background-secondary px-6 py-10 text-center">
      <Icon size={24} className="text-foreground-muted" aria-hidden="true" />
      <p className="text-sm font-medium text-foreground">{title}</p>
      {/* `foreground-muted`, never `foreground-subtle`: #64748b on this
          background is about 3.5:1, under the 4.5:1 minimum for body text. */}
      {hint && <p className="max-w-prose text-xs text-foreground-muted">{hint}</p>}
    </div>
  );
}
