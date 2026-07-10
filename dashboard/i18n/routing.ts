import { defineRouting } from "next-intl/routing";

/**
 * Supported dashboard locales. Must stay in sync with the bot templates,
 * the webapp locale JSONs, and backend app/core/languages.py SUPPORTED_LANGUAGES.
 * Russian is the default (operator/primary market language).
 */
export const routing = defineRouting({
  locales: ["ru", "uz", "tr", "fa", "zh"],
  defaultLocale: "ru",
});

export type Locale = (typeof routing.locales)[number];
