"use client";

import { Globe } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { usePathname, useRouter } from "@/i18n/navigation";
import { routing, type Locale } from "@/i18n/routing";

/**
 * Locale switcher. Re-navigates to the current path under the chosen locale
 * (next-intl router.replace with a { locale } option), so the URL /[locale]/
 * prefix and the NEXT_LOCALE cookie stay in sync.
 */
export function LanguageSwitcher() {
  const t = useTranslations("language");
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();

  return (
    <label className="flex items-center gap-2 text-xs text-foreground-muted">
      <Globe className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
      <span className="sr-only">{t("label")}</span>
      <select
        aria-label={t("label")}
        value={locale}
        onChange={(e) =>
          router.replace(pathname, { locale: e.target.value as Locale })
        }
        className="flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
      >
        {routing.locales.map((loc) => (
          <option key={loc} value={loc}>
            {t(loc)}
          </option>
        ))}
      </select>
    </label>
  );
}
