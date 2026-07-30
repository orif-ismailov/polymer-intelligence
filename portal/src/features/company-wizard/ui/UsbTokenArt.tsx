import { cn } from "@/shared/lib";

interface UsbTokenArtProps {
  className?: string;
}

/**
 * The E-IMZO key, drawn.
 *
 * The mockup shows a product photograph of a USB token; a raster asset would be
 * a second thing to ship, would not recolour with the theme, and would need a
 * light-theme twin. This traces the same object from tokens — graphite body,
 * metal connector, brand-lit status ring — so it belongs to the design system
 * rather than to `public/`.
 */
export function UsbTokenArt({ className }: UsbTokenArtProps) {
  return (
    <svg
      viewBox="0 0 240 110"
      className={cn("h-auto w-full max-w-[260px]", className)}
      fill="none"
      role="img"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="eimzo-body" x1="60" y1="10" x2="200" y2="100" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--surface-2)" />
          <stop offset="0.55" stopColor="var(--surface)" />
          <stop offset="1" stopColor="var(--bg)" />
        </linearGradient>
        <linearGradient id="eimzo-metal" x1="14" y1="46" x2="80" y2="86" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--border)" />
          <stop offset="0.5" stopColor="var(--border-strong)" />
          <stop offset="1" stopColor="var(--border)" />
        </linearGradient>
        <radialGradient id="eimzo-glow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="var(--brand)" stopOpacity="0.45" />
          <stop offset="1" stopColor="var(--brand)" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Cast light under the key, so it sits on the sheet rather than floating. */}
      <ellipse cx="150" cy="96" rx="74" ry="10" fill="url(#eimzo-glow)" />

      {/* Metal connector */}
      <path
        d="M18 52h58v30H18a4 4 0 0 1-4-4V56a4 4 0 0 1 4-4Z"
        fill="url(#eimzo-metal)"
        stroke="var(--border-strong)"
        strokeWidth="1.5"
      />
      <rect x="26" y="60" width="12" height="14" rx="1.5" fill="var(--bg)" />
      <rect x="46" y="60" width="12" height="14" rx="1.5" fill="var(--bg)" />

      {/* Body */}
      <path
        d="M76 34h108c22 0 40 14 40 33s-18 33-40 33H76a8 8 0 0 1-8-8V42a8 8 0 0 1 8-8Z"
        fill="url(#eimzo-body)"
        stroke="var(--border-strong)"
        strokeWidth="1.5"
      />
      {/* Moulded ridge along the top edge */}
      <path d="M96 46h64" stroke="var(--border)" strokeWidth="3" strokeLinecap="round" />
      <circle cx="176" cy="46" r="3" fill="var(--border)" />

      {/* Status ring — the key is present and lit */}
      <circle cx="180" cy="67" r="17" stroke="var(--brand)" strokeWidth="3.5" />
      <circle cx="180" cy="67" r="17" stroke="var(--brand)" strokeWidth="9" opacity="0.18" />
    </svg>
  );
}
