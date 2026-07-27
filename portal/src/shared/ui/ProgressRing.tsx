import { type HTMLAttributes } from "react";

import { cn } from "@/shared/lib";

interface ProgressRingProps extends Omit<HTMLAttributes<HTMLDivElement>, "children" | "role"> {
  /** Completion percentage, 0–100. Values outside the range are clamped. */
  value: number;
  /** Outer diameter in px. */
  size?: number;
  /** Ring thickness in px. */
  thickness?: number;
  /** Caption under the figure (e.g. "Проверка компании"). */
  label?: string;
  /** Accessible name — falls back to `label`. */
  ariaLabel?: string;
  className?: string;
}

/**
 * Circular progress dial — the "AI-проверка компании / 76%" screen in the
 * mockups. The arc is drawn with a stroke dash offset so it animates smoothly as
 * the value climbs; the figure is also rendered as text so it is readable
 * without colour vision, and the whole thing is a `progressbar` for AT.
 */
export function ProgressRing({
  value,
  size = 160,
  thickness = 10,
  label,
  ariaLabel,
  className,
  ...rest
}: ProgressRingProps) {
  const pct = Math.min(100, Math.max(0, Math.round(value)));
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - pct / 100);

  return (
    <div
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={ariaLabel ?? label}
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
      {...rest}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--border)"
          strokeWidth={thickness}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--brand)"
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          className="transition-[stroke-dashoffset] duration-500 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="num text-3xl font-semibold text-brand">{pct}%</span>
        {label ? <span className="mt-1 px-4 text-xs text-text-muted">{label}</span> : null}
      </div>
    </div>
  );
}
