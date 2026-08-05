import { cn } from "@/shared/lib";

interface BrandLogoProps {
  /** Show the "AI B2B PLATFORM" descriptor under the wordmark (mockup lockup). */
  withTagline?: boolean;
  /** Hide the wordmark, keeping only the mark (tight spaces). */
  markOnly?: boolean;
  /**
   * `md` is the cabinet lockup. `lg` is the storefront one: marketplace.jpeg
   * draws it at ~52px mark / 25px wordmark, roughly double the cabinet's, and
   * drops the divider. It steps down below `xl` so a phone bar still fits the
   * mark, wordmark, and the two CTAs beside them.
   */
  size?: "md" | "lg";
  className?: string;
}

const MARK_SIZE: Record<NonNullable<BrandLogoProps["size"]>, string> = {
  md: "h-7 w-7",
  lg: "h-9 w-9 xl:h-[3.25rem] xl:w-[3.25rem]",
};

/**
 * `lg` is widely tracked, not just larger: the mockup's wordmark measures 127px
 * against a 25px cap height, which only reconciles at ~0.26em letter-spacing.
 * `md` keeps the tight cabinet lockup.
 */
const WORDMARK_SIZE: Record<NonNullable<BrandLogoProps["size"]>, string> = {
  md: "text-[15px] tracking-tight",
  // Steps down twice: at 390px the full lockup plus the nav's CTA cluster
  // overflows the viewport, and wide tracking is what costs the most width.
  lg: "text-[15px] tracking-[0.06em] sm:text-[17px] sm:tracking-[0.22em] xl:text-[25px] xl:tracking-[0.26em]",
};

/**
 * IMEX AI lockup: the crossed-arrows mark (import × export) plus the wordmark,
 * drawn from tokens so it recolours with the theme.
 *
 * Interim asset — the mockups use a supplied vector logo which the operator has
 * not delivered yet (P0 T3.2). This keeps the chrome on-brand until then; swap
 * the <svg> here and every surface follows.
 */
export function BrandLogo({
  withTagline = false,
  markOnly = false,
  size = "md",
  className,
}: BrandLogoProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center",
        size === "lg" ? "gap-2.5 xl:gap-3.5" : "gap-2.5",
        className,
      )}
    >
      {/*
        Hexagon silhouette from marketplace.jpeg; crossed-arrows mark kept until
        the operator-supplied vector lands (P0 T3.2).
      */}
      <svg
        viewBox="0 0 28 28"
        fill="none"
        aria-hidden="true"
        className={cn("shrink-0", MARK_SIZE[size])}
      >
        <path
          d="M14 1.5 25.5 8v12L14 26.5 2.5 20V8L14 1.5Z"
          fill="var(--brand)"
        />
        <path
          d="M8.5 9.5l11 9M19.5 9.5l-11 9"
          stroke="var(--brand-fg)"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
      </svg>
      {markOnly ? null : (
        <>
          {/* The storefront lockup has no divider — marketplace.jpeg §1. */}
          {size === "lg" ? null : (
            <span aria-hidden className="hidden h-5 w-px bg-border-strong sm:block" />
          )}
          <span className="leading-none">
            <span
              className={cn("block font-semibold text-text", WORDMARK_SIZE[size])}
            >
              IMEX <span className="text-brand">AI</span>
            </span>
            {withTagline ? (
              <span className="mt-0.5 block text-[10px] uppercase tracking-[0.18em] text-text-subtle">
                AI B2B Platform
              </span>
            ) : null}
          </span>
        </>
      )}
    </span>
  );
}
