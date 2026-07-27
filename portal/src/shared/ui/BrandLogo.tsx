import { cn } from "@/shared/lib";

interface BrandLogoProps {
  /** Show the "AI B2B PLATFORM" descriptor under the wordmark (mockup lockup). */
  withTagline?: boolean;
  /** Hide the wordmark, keeping only the mark (tight spaces). */
  markOnly?: boolean;
  className?: string;
}

/**
 * IMEX AI lockup: the crossed-arrows mark (import × export) plus the wordmark,
 * drawn from tokens so it recolours with the theme.
 *
 * Interim asset — the mockups use a supplied vector logo which the operator has
 * not delivered yet (P0 T3.2). This keeps the chrome on-brand until then; swap
 * the <svg> here and every surface follows.
 */
export function BrandLogo({ withTagline = false, markOnly = false, className }: BrandLogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <svg
        width="28"
        height="28"
        viewBox="0 0 28 28"
        fill="none"
        aria-hidden="true"
        className="shrink-0"
      >
        <rect width="28" height="28" rx="8" fill="var(--brand)" />
        <path
          d="M8.5 9.5l11 9M19.5 9.5l-11 9"
          stroke="var(--brand-fg)"
          strokeWidth="2.6"
          strokeLinecap="round"
        />
      </svg>
      {markOnly ? null : (
        <span className="leading-none">
          <span className="block font-semibold tracking-tight text-text">
            IMEX <span className="text-brand">AI</span>
          </span>
          {withTagline ? (
            <span className="mt-0.5 block text-[10px] uppercase tracking-[0.18em] text-text-subtle">
              AI B2B Platform
            </span>
          ) : null}
        </span>
      )}
    </span>
  );
}
