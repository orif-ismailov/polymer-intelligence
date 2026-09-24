import Image from "next/image";

import logo from "@/public/brand/logo-imex-dark.png";

/**
 * The IMEX lockup — the same artwork the portal uses (`portal/public/
 * logo-imex-dark.png`), in its light-on-dark cut because the dashboard is dark
 * only. The image carries the wordmark, so no text is set beside it; `alt` is
 * the name a screen reader announces in its place.
 *
 * A static import rather than a `/brand/…` string: Next fingerprints it into
 * `.next/static`, so a replaced logo is never served stale from a cache.
 */
export function BrandLogo({ className }: { className?: string }) {
  // `sizes`: the lockup never renders wider than ~130px; without it Next picks
  // the 1080px variant for a 40px-tall image.
  return <Image src={logo} alt="IMEX" priority sizes="160px" className={className} />;
}
