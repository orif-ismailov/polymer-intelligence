import { useTranslation } from "react-i18next";

import { coerceLang, SUPPORTED_LANGS, setLanguage } from "@/shared/i18n";
import type { Lang } from "@/shared/i18n";
import { GlobeIcon, Select } from "@/shared/ui";

interface LanguageMenuProps {
  /**
   * `compact` is the mockups' entry-sheet treatment — a globe and the two-letter
   * code, sized to sit in a header's glyph slot beside a ✕. The default is the
   * named select the login card uses.
   */
  compact?: boolean;
}

/** Language switcher for the unauthenticated / full-screen flow chrome. */
export function LanguageMenu({ compact = false }: LanguageMenuProps) {
  const { t, i18n } = useTranslation();
  const current = coerceLang(i18n.language);

  if (!compact) {
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

  return (
    <span className="relative inline-flex items-center gap-1.5 text-text">
      <GlobeIcon size={18} />
      <span className="text-sm font-medium">{current.toUpperCase()}</span>
      {/* The native select is stretched invisibly over the pair, so the whole
          thing is one tap target and the platform picker still does the work. */}
      <select
        aria-label={t("settings.language")}
        value={current}
        onChange={(e) => setLanguage(e.target.value as Lang)}
        className="absolute inset-0 cursor-pointer opacity-0"
      >
        {SUPPORTED_LANGS.map((lang) => (
          <option key={lang} value={lang}>
            {t(`language.${lang}`)}
          </option>
        ))}
      </select>
    </span>
  );
}
