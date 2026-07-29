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

/** Left chevron — the mockups' "‹ Назад" affordance on every detail screen. */
export function ChevronLeftIcon({ size = 14, className }: IconProps) {
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
        d="M10 3.2 5.2 8l4.8 4.8"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Right chevron — "open this row" on list cards and directory rows. */
export function ChevronRightIcon({ size = 14, className }: IconProps) {
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
        d="M6 3.2 10.8 8 6 12.8"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Tray with a down arrow — the download affordance on document rows. */
export function DownloadIcon({ size = 14, className }: IconProps) {
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
        d="M8 2.6v6.6m0 0L5.4 6.6M8 9.2l2.6-2.6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M2.8 11v1.2a1.2 1.2 0 0 0 1.2 1.2h8a1.2 1.2 0 0 0 1.2-1.2V11"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Dog-eared sheet — the document glyph on file rows. */
export function FileIcon({ size = 14, className }: IconProps) {
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
        d="M9.2 1.8H4.6a1.2 1.2 0 0 0-1.2 1.2v10a1.2 1.2 0 0 0 1.2 1.2h6.8a1.2 1.2 0 0 0 1.2-1.2V5.2L9.2 1.8Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path d="M9.2 1.8v3.4h3.4" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}

/** Circled "i" — the mockups mark explainable fields with one. */
export function InfoIcon({ size = 14, className }: IconProps) {
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
      <path d="M8 7.2v3.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="8" cy="5.2" r="0.85" fill="currentColor" />
    </svg>
  );
}

/** Shield with a tick — "safe and legal" reassurance blocks. */
export function ShieldIcon({ size = 14, className }: IconProps) {
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
        d="M8 1.8 3.2 3.6v4.2c0 2.8 2 5.2 4.8 6.4 2.8-1.2 4.8-3.6 4.8-6.4V3.6L8 1.8Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path
        d="M5.9 7.9 7.4 9.4l2.9-3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
