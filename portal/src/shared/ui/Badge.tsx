import { type HTMLAttributes, type ReactNode } from "react";

import { cn } from "@/shared/lib";

import { BoxIcon, CheckCircleIcon, ClockIcon, FlaskIcon } from "./icons";

export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info" | "brand" | "gold";

/**
 * The recurring badges from the mockups, named by meaning rather than colour so
 * pages never pick the tone (or the glyph) themselves. Anything outside this set
 * still uses a plain `tone`.
 */
export type BadgeVariant = "verified" | "lab-verified" | "in-stock" | "on-order";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  /** Semantic preset — supplies both the tone and the mockup's glyph. */
  variant?: BadgeVariant;
  /** Leading glyph. Ignored when `variant` provides one. */
  icon?: ReactNode;
}

const tones: Record<BadgeTone, string> = {
  neutral: "bg-surface-2 text-text-muted border-border",
  success: "bg-success/10 text-success border-success/30",
  warning: "bg-warning/10 text-warning border-warning/30",
  danger: "bg-danger/10 text-danger border-danger/30",
  info: "bg-info/10 text-info border-info/30",
  brand: "bg-brand-soft text-brand border-brand-line",
  gold: "bg-gold-soft text-gold border-gold-line",
};

const variants: Record<BadgeVariant, { tone: BadgeTone; icon: ReactNode }> = {
  verified: { tone: "brand", icon: <CheckCircleIcon /> },
  "lab-verified": { tone: "gold", icon: <FlaskIcon /> },
  "in-stock": { tone: "success", icon: <BoxIcon /> },
  "on-order": { tone: "neutral", icon: <ClockIcon /> },
};

export function Badge({
  tone = "neutral",
  variant,
  icon,
  className,
  children,
  ...rest
}: BadgeProps) {
  const preset = variant ? variants[variant] : null;
  const glyph = preset ? preset.icon : icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        tones[preset ? preset.tone : tone],
        className,
      )}
      {...rest}
    >
      {glyph}
      {children}
    </span>
  );
}
