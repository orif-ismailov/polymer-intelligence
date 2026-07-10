/**
 * i18next configuration for the Telegram Web App.
 *
 * Six locales — ru (default), en, tr, uz, fa (Persian, RTL), zh (Chinese).
 * Language default (D-04): prefer the user's persisted choice, else read Telegram
 * language_code on first boot, else ru. Persisted to localStorage and read back on
 * subsequent boots. The <html dir> attribute is set to "rtl" for right-to-left
 * languages (fa) and "ltr" otherwise, on init and on every language change.
 */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./en.json";
import fa from "./fa.json";
import ru from "./ru.json";
import tr from "./tr.json";
import uz from "./uz.json";
import zh from "./zh.json";

export const SUPPORTED_LANGS = ["ru", "en", "tr", "uz", "fa", "zh"] as const;
export type Lang = (typeof SUPPORTED_LANGS)[number];

/** Right-to-left locales — drive the <html dir> attribute. */
export const RTL_LANGS: readonly Lang[] = ["fa"];

/** Text direction for a language code (used for the <html dir> attribute). */
export function dirFor(lang: string): "rtl" | "ltr" {
  return (RTL_LANGS as readonly string[]).includes(lang) ? "rtl" : "ltr";
}

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
    if (langCode.startsWith("fa")) return "fa";
    if (langCode.startsWith("zh")) return "zh";
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
    fa: { translation: fa },
    zh: { translation: zh },
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
  document.documentElement.dir = dirFor(lng);
});

// Set initial <html lang> + text direction (rtl for fa)
document.documentElement.lang = detectedLang;
document.documentElement.dir = dirFor(detectedLang);

export default i18n;
