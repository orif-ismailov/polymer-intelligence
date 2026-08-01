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

/**
 * The user's own language preference: persisted choice → browser → default.
 *
 * NOT what i18n initializes with under SSR. See {@link detectLanguage}.
 */
export function preferredLanguage(): Lang {
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

/**
 * The language i18n initializes with.
 *
 * On a server-rendered page this MUST be the language the server rendered in,
 * not the one the browser would pick. When the two disagreed, every string in
 * the tree differed from the markup and React failed hydration outright,
 * discarded the server's HTML and re-rendered from scratch — which silently
 * costs the whole reason SSR was added. The server injects what it used;
 * `AppBootstrap` switches to the user's actual preference AFTER hydration,
 * where a change is just a re-render.
 */
export function detectLanguage(): Lang {
  const ssr = (globalThis as { __SSR_LANG__?: string }).__SSR_LANG__;
  if (ssr && isLang(ssr)) return ssr;
  return preferredLanguage();
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
    // Also a cookie, because localStorage is invisible to the SSR server. With
    // it, a returning visitor's page is RENDERED in their language instead of
    // being rendered in the default and corrected after hydration, which is the
    // difference between a clean load and a visible flash of the wrong language.
    // Lax + one year: a display preference, not a credential.
    document.cookie = `${LANGUAGE_KEY}=${lang}; path=/; max-age=31536000; samesite=lax`;
  }
}

export default i18n;
