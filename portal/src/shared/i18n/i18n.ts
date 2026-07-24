import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import { LANGUAGE_KEY } from "@/shared/config";

import en from "./locales/en.json";
import ru from "./locales/ru.json";
import uz from "./locales/uz.json";

export const SUPPORTED_LANGS = ["ru", "uz", "en"] as const;
export type Lang = (typeof SUPPORTED_LANGS)[number];

export const DEFAULT_LANG: Lang = "ru";

function isLang(value: string): value is Lang {
  return (SUPPORTED_LANGS as readonly string[]).includes(value);
}

/** Detect the initial language: persisted choice → browser → default. */
export function detectLanguage(): Lang {
  try {
    const stored = localStorage.getItem(LANGUAGE_KEY);
    if (stored && isLang(stored)) return stored;
  } catch {
    // localStorage unavailable (private mode / SSR) — fall through.
  }
  const nav = typeof navigator !== "undefined" ? navigator.language.slice(0, 2) : "";
  if (isLang(nav)) return nav;
  return DEFAULT_LANG;
}

/** Coerce an arbitrary backend language string into a supported UI language. */
export function coerceLang(value: string | null | undefined): Lang {
  if (value && isLang(value)) return value;
  return DEFAULT_LANG;
}

void i18n.use(initReactI18next).init({
  resources: {
    ru: { translation: ru },
    uz: { translation: uz },
    en: { translation: en },
  },
  lng: detectLanguage(),
  fallbackLng: DEFAULT_LANG,
  supportedLngs: [...SUPPORTED_LANGS],
  interpolation: { escapeValue: false },
  returnNull: false,
});

/** Change the active language and persist the choice. */
export function setLanguage(lang: Lang): void {
  void i18n.changeLanguage(lang);
  try {
    localStorage.setItem(LANGUAGE_KEY, lang);
  } catch {
    // Persistence is best-effort.
  }
  if (typeof document !== "undefined") {
    document.documentElement.lang = lang;
  }
}

export default i18n;
