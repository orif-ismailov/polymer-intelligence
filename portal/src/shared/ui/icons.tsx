/**
 * Inline icon set for the design system. The portal deliberately ships no icon
 * dependency (see the hand-rolled SVGs in widgets/app-shell) — these are the
 * handful the shared primitives need, so pages don't re-draw them per screen.
 *
 * All of them inherit `currentColor` and size from the `size` prop, so a badge
 * or button controls the colour through tokens.
 */

interface IconProps {
  size?: number;
  className?: string;
}

/** Filled circle with a tick — Verified / passed check (mockup badge glyph). */
export function CheckCircleIcon({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="7" fill="currentColor" />
      <path
        d="M4.8 8.3l2.1 2.1 4.3-4.6"
        stroke="var(--surface)"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Bare tick, for use inside an already-filled circle (steppers). */
export function CheckIcon({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M3.5 8.4l3 3 6-6.8"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Laboratory flask — the Laboratory Verified badge glyph. */
export function FlaskIcon({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M6 2h4M6.6 2v3.4L3.5 11.2A1.6 1.6 0 0 0 4.9 13.6h6.2a1.6 1.6 0 0 0 1.4-2.4L9.4 5.4V2"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M4.6 9.6h6.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

/** Stacked boxes — "in stock" availability. */
export function BoxIcon({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M2.5 5.2 8 2.4l5.5 2.8v5.6L8 13.6 2.5 10.8V5.2Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path d="M2.5 5.2 8 8m0 0 5.5-2.8M8 8v5.6" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

/** Clock — "made to order" / lead time. */
export function ClockIcon({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="5.8" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8 4.8V8l2.2 1.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
