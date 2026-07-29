import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

import { FileIcon } from "./icons";

interface FileRowProps {
  name: string;
  /** Meta line under the name — the mockups show "PDF · 1.2 MB · 12.05.2024". */
  meta?: ReactNode;
  icon?: ReactNode;
  /** Status badge on the right of the name (verification docs carry one). */
  status?: ReactNode;
  /** Trailing controls: download, remove. */
  actions?: ReactNode;
  /** Strikes the name through — a revoked or superseded document. */
  muted?: boolean;
  className?: string;
}

/**
 * A document row: glyph, name, meta line, optional status, trailing actions.
 * The mockups render every attachment this way (company documents, contract PDF,
 * offer SDS/TDS/COA, lab passport), and five call sites had each drawn their own.
 */
export function FileRow({
  name,
  meta,
  icon,
  status,
  actions,
  muted = false,
  className,
}: FileRowProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md border border-border bg-surface px-3 py-2.5",
        className,
      )}
      data-testid="ui-file-row"
    >
      <span className="shrink-0 text-text-subtle">{icon ?? <FileIcon size={18} />}</span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p
            className={cn(
              "truncate text-sm font-medium text-text",
              muted && "text-text-subtle line-through",
            )}
            title={name}
          >
            {name}
          </p>
          {status}
        </div>
        {meta ? <p className="num mt-0.5 text-xs text-text-subtle">{meta}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-1">{actions}</div> : null}
    </div>
  );
}
