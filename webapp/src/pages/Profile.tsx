/**
 * Профиль tab — appearance (theme), language, and role preference.
 *
 * Theme: system/light/dark via the theme store (system follows Telegram's
 * colorScheme). Language: ru/en/tr/uz — switches i18n immediately (optimistic) and
 * persists to the profile. Role: buyer/seller (the default-tab hint, switchable).
 */

import { useEffect, useState, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Send } from "lucide-react";

import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import ErrorBanner from "../components/ErrorBanner";
import Segmented from "../components/Segmented";
import Button from "../components/Button";
import { useTheme, type ThemePref } from "../theme/themeStore";
import { useRoleStore, type Role } from "../store/roleStore";
import { SUPPORTED_LANGS, type Lang } from "../i18n";

const sectionLabel: CSSProperties = {
  margin: "0 0 10px",
  fontSize: "13px",
  fontWeight: 600,
  color: "var(--text-muted)",
};

export default function Profile() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { pref, setPref } = useTheme();
  const role = useRoleStore((s) => s.role);
  const setRole = useRoleStore((s) => s.setRole);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    backButton.hide();
    mainButton.hide();
  }, []);

  const currentLang: Lang = (SUPPORTED_LANGS as readonly string[]).includes(i18n.language)
    ? (i18n.language as Lang)
    : "ru";

  async function changeLang(lang: Lang) {
    if (lang === currentLang) return;
    void i18n.changeLanguage(lang); // optimistic — switch UI immediately
    setError(null);
    try {
      await api.patchMe({ language: lang });
    } catch {
      setError(t("error.loadFailed"));
    }
  }

  const themeOptions: { value: ThemePref; label: string }[] = [
    { value: "system", label: t("settings.themeOpt.system") },
    { value: "light", label: t("settings.themeOpt.light") },
    { value: "dark", label: t("settings.themeOpt.dark") },
  ];
  const langOptions = SUPPORTED_LANGS.map((l) => ({ value: l, label: t(`settings.lang.${l}`) }));
  const roleOptions: { value: string; label: string }[] = [
    { value: "buyer", label: t("profile.roleOpt.buyer") },
    { value: "seller", label: t("profile.roleOpt.seller") },
  ];

  return (
    <div style={{ padding: "16px" }}>
      <h1 style={{ margin: "0 0 20px", fontSize: "20px", fontWeight: 700, color: "var(--text)" }}>
        {t("profile.title")}
      </h1>

      {error && <ErrorBanner message={error} />}

      <section style={{ marginBottom: "24px" }}>
        <p style={sectionLabel}>{t("settings.theme")}</p>
        <Segmented<ThemePref>
          value={pref}
          options={themeOptions}
          onChange={setPref}
          ariaLabel={t("settings.theme")}
        />
      </section>

      <section style={{ marginBottom: "24px" }}>
        <p style={sectionLabel}>{t("settings.language")}</p>
        <Segmented<Lang>
          value={currentLang}
          options={langOptions}
          onChange={(l) => void changeLang(l)}
          ariaLabel={t("settings.language")}
        />
      </section>

      <section style={{ marginBottom: "24px" }}>
        <p style={sectionLabel}>{t("profile.role")}</p>
        <Segmented<string>
          value={role ?? ""}
          options={roleOptions}
          onChange={(r) => setRole(r as Role)}
          ariaLabel={t("profile.role")}
        />
      </section>

      <section>
        <p style={sectionLabel}>{t("support.title")}</p>
        <Button variant="telegram" onClick={() => navigate("/support")}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
            <Send size={18} /> {t("support.cta")}
          </span>
        </Button>
      </section>
    </div>
  );
}
