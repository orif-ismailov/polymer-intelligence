/**
 * C-09 — Settings / Language & Profile screen ("Язык и профиль").
 *
 * Two-option segmented control (Русский / O'zbek) bound to current i18n language.
 * On change:
 *   1. PATCH /webapp/me { language } — persist to server
 *   2. i18n.changeLanguage(language) immediately (no reload)
 *   3. localStorage persisted automatically via i18n.on('languageChanged') handler
 *   4. <html lang> updated automatically via same handler
 *
 * Optimistic UX: UI switches immediately even if PATCH fails (ErrorBanner shown).
 * No server-side language toggle means no visible delay (D-04).
 *
 * BackButton → Home (/). No MainButton (non-wizard screen).
 *
 * T-03-19: PATCH /webapp/me scoped to verified client — no client_id sent in body.
 */

import { useEffect, useState, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { styles } from "../App";
import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import ErrorBanner from "../components/ErrorBanner";

type Language = "ru" | "uz" | "tr";

export default function Settings() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  // Current language from i18n (initialized from localStorage/TG lang_code)
  const currentLang: Language =
    i18n.language === "uz" ? "uz" : i18n.language === "tr" ? "tr" : "ru";

  // Telegram BackButton → Home
  useEffect(() => {
    backButton.show();
    const cleanup = backButton.onClick(() => navigate("/"));
    mainButton.hide();
    return () => {
      cleanup();
      backButton.hide();
    };
  }, [navigate]);

  async function handleLanguageChange(lang: Language) {
    if (lang === currentLang) return;

    // Optimistic: switch UI language immediately (no reload, D-04)
    void i18n.changeLanguage(lang);
    setError(null);

    // Persist to server (T-03-19: no client_id in body — scoped by initData)
    try {
      await api.patchMe({ language: lang });
    } catch {
      // ErrorBanner shown but UI language stays switched (optimistic)
      setError(t("error.loadFailed"));
    }
  }

  const segmentBase: CSSProperties = {
    flex: 1,
    minHeight: "44px",
    padding: "10px 16px",
    border: "none",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    transition: "background-color 0.15s ease",
    boxSizing: "border-box" as const,
  };

  const activeSegment: CSSProperties = {
    ...segmentBase,
    backgroundColor: "var(--green)",
    color: "var(--green-on)",
  };

  const inactiveSegment: CSSProperties = {
    ...segmentBase,
    backgroundColor: "var(--surface)",
    color: "var(--text-muted)",
  };

  return (
    <div style={{ ...styles.app }}>
      {/* Screen header */}
      <div style={styles.header as CSSProperties}>
        <h1 style={styles.headerTitle}>{t("settings.title")}</h1>
      </div>

      <div style={{ padding: "16px" }}>
        {/* Error banner */}
        {error && <ErrorBanner message={error} />}

        {/* Language section card */}
        <div style={{ ...styles.card as CSSProperties }}>
          <p
            style={{
              margin: "0 0 12px",
              fontSize: "13px",
              color: "var(--text-muted)",
            } as CSSProperties}
          >
            {t("settings.language")}
          </p>

          {/* Segmented control: RU / UZ */}
          <div
            role="group"
            aria-label={t("settings.language")}
            style={{
              display: "flex",
              borderRadius: "var(--r-md)",
              overflow: "hidden",
              border: "1px solid var(--border)",
            } as CSSProperties}
          >
            <button
              type="button"
              aria-pressed={currentLang === "ru"}
              onClick={() => void handleLanguageChange("ru")}
              style={currentLang === "ru" ? activeSegment : inactiveSegment}
            >
              {t("settings.lang.ru")}
            </button>
            <button
              type="button"
              aria-pressed={currentLang === "uz"}
              onClick={() => void handleLanguageChange("uz")}
              style={currentLang === "uz" ? activeSegment : inactiveSegment}
            >
              {t("settings.lang.uz")}
            </button>
            <button
              type="button"
              aria-pressed={currentLang === "tr"}
              onClick={() => void handleLanguageChange("tr")}
              style={currentLang === "tr" ? activeSegment : inactiveSegment}
            >
              {t("settings.lang.tr")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
