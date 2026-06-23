/**
 * i18next configuration for the Telegram Web App.
 *
 * Language default (D-04): read Telegram language_code on first boot;
 * set to 'uz' if it starts with 'uz', else 'ru'. Persisted to localStorage
 * and read back on subsequent boots.
 */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import ru from "./ru.json";
import uz from "./uz.json";

/** Detect language from Telegram SDK or window.Telegram.WebApp, fallback to 'ru'. */
function detectLanguage(): string {
  // 1. Prefer localStorage (user's explicit or persisted choice)
  const stored = localStorage.getItem("pi_language");
  if (stored === "ru" || stored === "uz") return stored;

  // 2. Telegram language_code from legacy window.Telegram.WebApp
  try {
    const tg = (window as unknown as { Telegram?: { WebApp?: { initDataUnsafe?: { user?: { language_code?: string } } } } })
      .Telegram?.WebApp;
    const langCode = tg?.initDataUnsafe?.user?.language_code ?? "";
    if (langCode.startsWith("uz")) return "uz";
  } catch {
    // fall through
  }

  return "ru";
}

const detectedLang = detectLanguage();

i18n
  .use(initReactI18next)
  .init({
    resources: {
      ru: { translation: ru },
      uz: { translation: uz },
    },
    lng: detectedLang,
    fallbackLng: "ru",
    interpolation: {
      escapeValue: false, // React already escapes
    },
  });

// Persist language choice and update <html lang> on change
i18n.on("languageChanged", (lng) => {
  localStorage.setItem("pi_language", lng);
  document.documentElement.lang = lng;
});

// Set initial <html lang>
document.documentElement.lang = detectedLang;

export default i18n;
