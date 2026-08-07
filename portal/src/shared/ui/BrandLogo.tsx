import { cn } from "@/shared/lib";

interface BrandLogoProps {
  /** Show the "AI B2B PLATFORM" descriptor under the wordmark (mockup lockup). */
  withTagline?: boolean;
  /**
   * `md` is the cabinet lockup. `lg` is the storefront one — larger, and
   * stepping up again at `xl` where the nav has room (mockup draws it at
   * roughly double the cabinet size).
   */
  size?: "md" | "lg";
  className?: string;
}

const LOGO_SIZE: Record<NonNullable<BrandLogoProps["size"]>, string> = {
  md: "h-9",
  lg: "h-10 xl:h-14",
};

/**
 * The operator-supplied IMEX wordmark (P0 T3.2 — this replaced the interim
 * hexagon + text lockup). One asset per theme: the letters are white on the
 * dark theme and near-black on the light one, so this cannot recolour with
 * tokens the way the old inline SVG did. Both files share one crop box, so
 * they swap 1:1; the toggle is CSS (`dark:` = `[data-theme="dark"]`), which
 * keeps the server render theme-agnostic — no hydration mismatch.
 *
 * `alt="IMEX AI"` is deliberate: every BrandLogo is wrapped in a link to `/`,
 * and the link's accessible name comes from this alt (e2e clicks the logo by
 * that name).
 */
export function BrandLogo({
  withTagline = false,
  size = "md",
  className,
}: BrandLogoProps) {
  return (
    <span className={cn("inline-flex flex-col items-start", className)}>
      <img
        src="/logo-imex-light.png"
        alt="IMEX AI"
        className={cn("w-auto dark:hidden", LOGO_SIZE[size])}
      />
      <img
        src="/logo-imex-dark.png"
        alt="IMEX AI"
        className={cn("hidden w-auto dark:block", LOGO_SIZE[size])}
      />
      {withTagline ? (
        <span className="mt-1 block text-[10px] uppercase tracking-[0.18em] text-text-subtle">
          AI B2B Platform
        </span>
      ) : null}
    </span>
  );
}
