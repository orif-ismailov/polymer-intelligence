import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

export type IconTileTone = "muted" | "brand" | "gold" | "danger";
export type IconTileSize = "sm" | "md";

interface IconTileProps {
  children: ReactNode;
  tone?: IconTileTone;
  size?: IconTileSize;
  className?: string;
}

/**
 * The rounded-square glyph holder the mockups put in front of a row's title —
 * account-type cards, verification checks, instruction blocks.
 *
 * `muted` is the resting state (inset well, subdued glyph); `brand` is the one
 * that has been chosen or has passed, and lights the glyph green over a soft
 * brand wash. Callers pick the meaning, never the colours.
 */
const tones: Record<IconTileTone, string> = {
  muted: "border-border bg-surface-inset text-text-muted",
  brand: "border-brand-line bg-brand-soft text-brand",
  gold: "border-gold-line bg-gold-soft text-gold",
  danger: "border-danger/30 bg-danger/10 text-danger",
};

const sizes: Record<IconTileSize, string> = {
  sm: "h-9 w-9 rounded-sm",
  md: "h-11 w-11 rounded-md",
};

export function IconTile({ children, tone = "muted", size = "md", className }: IconTileProps) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center border transition-colors",
        tones[tone],
        sizes[size],
        className,
      )}
    >
      {children}
    </span>
  );
}
