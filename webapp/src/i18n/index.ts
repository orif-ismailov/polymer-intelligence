/**
 * i18next configuration for the Telegram Web App.
 *
 * Four locales — ru (default), en, tr, uz. Language default (D-04): prefer the
 * user's persisted choice, else read Telegram language_code on first boot, else ru.
 * Persisted to localStorage and read back on subsequent boots.
 */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./en.json";
import ru from "./ru.json";
import tr from "./tr.json";
import uz from "./uz.json";

export const SUPPORTED_LANGS = ["ru", "en", "tr", "uz"] as const;
export type Lang = (typeof SUPPORTED_LANGS)[number];

function isLang(v: string): v is Lang {
  return (SUPPORTED_LANGS as readonly string[]).includes(v);
}

/** Detect language from localStorage or the Telegram SDK, fallback to 'ru'. */
function detectLanguage(): Lang {
  // 1. Prefer localStorage (user's explicit or persisted choice)
  try {
    const stored = localStorage.getItem("pi_language");
    if (stored && isLang(stored)) return stored;
  } catch {
    /* ignore */
  }

  // 2. Telegram language_code from the legacy window.Telegram.WebApp
  try {
    const tg = (
      window as unknown as {
        Telegram?: { WebApp?: { initDataUnsafe?: { user?: { language_code?: string } } } };
      }
    ).Telegram?.WebApp;
    const langCode = tg?.initDataUnsafe?.user?.language_code ?? "";
    if (langCode.startsWith("en")) return "en";
    if (langCode.startsWith("uz")) return "uz";
    if (langCode.startsWith("tr")) return "tr";
  } catch {
    /* fall through */
  }

  return "ru";
}

const detectedLang = detectLanguage();

i18n.use(initReactI18next).init({
  resources: {
    ru: { translation: ru },
    en: { translation: en },
    uz: { translation: uz },
    tr: { translation: tr },
  },
  lng: detectedLang,
  fallbackLng: "ru",
  interpolation: {
    escapeValue: false, // React already escapes
  },
});

// Persist language choice and update <html lang> on change
i18n.on("languageChanged", (lng) => {
  try {
    localStorage.setItem("pi_language", lng);
  } catch {
    /* ignore */
  }
  document.documentElement.lang = lng;
});

// Set initial <html lang>
document.documentElement.lang = detectedLang;

export default i18n;
