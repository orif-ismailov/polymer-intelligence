/**
 * LanguageSwitcher — compact globe pill + dropdown for the app header.
 *
 * Shows the active language code (RU/EN/UZ/TR); tapping opens a menu of the four
 * locales. Selecting one switches i18n immediately (optimistic) and persists it to
 * the client profile via PATCH /webapp/me — same behaviour as the Профиль page.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Globe, Check, ChevronDown } from "lucide-react";

import { api } from "../api/client";
import { SUPPORTED_LANGS, type Lang } from "../i18n";

export default function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);

  const current: Lang = (SUPPORTED_LANGS as readonly string[]).includes(i18n.language)
    ? (i18n.language as Lang)
    : "ru";

  async function choose(lang: Lang) {
    setOpen(false);
    if (lang === current) return;
    void i18n.changeLanguage(lang); // optimistic — switch UI immediately
    try {
      await api.patchMe({ language: lang });
    } catch {
      /* optimistic — UI stays switched even if persistence fails */
    }
  }

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t("settings.language")}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
          minHeight: "36px",
          padding: "6px 10px",
          borderRadius: "var(--r-full)",
          border: "1px solid var(--border)",
          background: "var(--surface)",
          color: "var(--text)",
          fontSize: "13px",
          fontWeight: 600,
          cursor: "pointer",
        }}
      >
        <Globe size={16} color="var(--text-muted)" />
        {current.toUpperCase()}
        <ChevronDown size={14} color="var(--text-muted)" />
      </button>

      {open && (
        <>
          {/* click-away backdrop */}
          <div
            onClick={() => setOpen(false)}
            style={{ position: "fixed", inset: 0, zIndex: 60 }}
            aria-hidden="true"
          />
          <ul
            role="listbox"
            style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              right: 0,
              zIndex: 61,
              listStyle: "none",
              margin: 0,
              padding: "6px",
              minWidth: "170px",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--r-md)",
              boxShadow: "var(--shadow)",
            }}
          >
            {SUPPORTED_LANGS.map((l) => (
              <li key={l}>
                <button
                  type="button"
                  role="option"
                  aria-selected={l === current}
                  onClick={() => void choose(l)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    width: "100%",
                    minHeight: "44px",
                    padding: "8px 10px",
                    background: l === current ? "var(--surface-2)" : "transparent",
                    border: "none",
                    color: "var(--text)",
                    fontSize: "14px",
                    fontWeight: l === current ? 600 : 400,
                    cursor: "pointer",
                    borderRadius: "var(--r-sm)",
                    textAlign: "left",
                  }}
                >
                  {t(`settings.lang.${l}`)}
                  {l === current && <Check size={16} color="var(--green)" />}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
