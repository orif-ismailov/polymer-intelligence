"use client";

import { ShieldOff } from "lucide-react";
import { useTranslations } from "next-intl";

/**
 * What a staff account sees for a page it has not been granted.
 *
 * The sidebar hides links the user cannot use, but a typed URL bypasses that —
 * and without this the page would mount, fire its queries, and paint a wall of
 * `API request failed: 403 Forbidden`. That reads as an outage rather than as a
 * permission boundary, and sends people to report a bug that isn't one.
 *
 * Distinct from `NoAccessNotice`, which replaces the whole shell for someone who
 * can reach NOTHING. Here the shell stays: the person has other pages, and the
 * nav is how they get back to one.
 *
 * This is a RENDERING decision, not a security one — every request the page would
 * have made is refused server-side by `require_page` regardless.
 */
export function NoPageAccess() {
  const t = useTranslations("noAccess");
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-6 text-center">
      <ShieldOff size={28} className="text-foreground-muted" aria-hidden="true" />
      <h2 className="text-lg font-semibold text-foreground">{t("pageTitle")}</h2>
      <p className="max-w-md text-sm text-foreground-muted">{t("pageBody")}</p>
    </div>
  );
}
