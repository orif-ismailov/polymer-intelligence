import { useTranslation } from "react-i18next";

import { coerceLang, SUPPORTED_LANGS, setLanguage } from "@/shared/i18n";
import type { Lang } from "@/shared/i18n";
import { Select } from "@/shared/ui";

/** Compact language switcher for the unauthenticated auth screens. */
export function LanguageMenu() {
  const { t, i18n } = useTranslation();
  const current = coerceLang(i18n.language);

  return (
    <Select
      aria-label={t("settings.language")}
      className="h-9 w-auto"
      value={current}
      options={SUPPORTED_LANGS.map((lang) => ({ value: lang, label: t(`language.${lang}`) }))}
      onChange={(e) => setLanguage(e.target.value as Lang)}
    />
  );
}
