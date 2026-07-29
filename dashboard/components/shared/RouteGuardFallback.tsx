"use client";

import { useTranslations } from "next-intl";

/**
 * What a route guard renders while it resolves.
 *
 * The guards are effect-driven (silent token refresh, or the non-admin bounce back
 * to `/`), so there is a beat between mount and redirect. Returning `null` for it
 * showed a solid black viewport for a few hundred milliseconds — indistinguishable
 * from a crash. A spinner says "working", which is the truth.
 */
export function RouteGuardFallback({ label }: { label?: string }) {
  const t = useTranslations("common");
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex h-full min-h-[60vh] flex-col items-center justify-center gap-3"
    >
      <div
        className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent"
        aria-hidden="true"
      />
      <p className="text-sm text-foreground-muted">{label ?? t("loading")}</p>
    </div>
  );
}
