import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

interface SpecTileProps {
  icon?: ReactNode;
  label: ReactNode;
  value: ReactNode;
  numeric?: boolean;
  className?: string;
}

/**
 * The mockups' bordered fact tile — the CAS / HS Code / Страна row on the product
 * sheet, and the FCA · Гомополимер · MOQ · Доставка strip on the market card.
 *
 * Not a `StatChip` variant: StatChip is figure-first (a big number over a caption,
 * with the figure pinned as its own test id) while this is label-first with a
 * glyph. Different DOM order, different job.
 */
export function SpecTile({ icon, label, value, numeric = false, className }: SpecTileProps) {
  return (
    <div
      className={cn("rounded-md border border-border bg-surface px-3 py-2.5", className)}
      data-testid="ui-spec-tile"
    >
      <div className="flex items-center gap-1.5 text-xs text-text-muted">
        {icon ? <span className="shrink-0 text-text-subtle">{icon}</span> : null}
        <span className="truncate">{label}</span>
      </div>
      <p className={cn("mt-0.5 text-sm font-medium text-text", numeric && "num")}>{value}</p>
    </div>
  );
}
