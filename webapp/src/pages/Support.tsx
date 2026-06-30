/**
 * Support — the "Чат-поддержка" screen (design_2 buyer ⑤).
 *
 * A centered Telegram glyph + reassurance copy + a blue CTA that opens the PetroAI
 * support chat in Telegram. Full-screen; BackButton returns to the previous screen.
 *
 * The support handle is a build-time constant; swap SUPPORT_URL for the real one.
 */

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Send } from "lucide-react";

import { backButton, mainButton } from "../telegram";

// PetroAI support group (Telegram invite link).
const SUPPORT_URL = "https://t.me/+Bx90bauleYY0NTFi";

export default function Support() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  useEffect(() => {
    backButton.show();
    const cleanup = backButton.onClick(() => navigate(-1));
    mainButton.hide();
    return () => {
      cleanup();
      backButton.hide();
    };
  }, [navigate]);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg)",
        color: "var(--text)",
        padding: "48px 24px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
      }}
    >
      <span
        style={{
          width: "84px",
          height: "84px",
          borderRadius: "var(--r-full)",
          background: "var(--chip-neutral-bg)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: "24px",
        }}
      >
        <Send size={38} color="var(--blue)" />
      </span>

      <h1 style={{ margin: "0 0 12px", fontSize: "22px", fontWeight: 700 }}>{t("support.title")}</h1>
      <p style={{ margin: "0 0 32px", fontSize: "15px", lineHeight: 1.5, color: "var(--text-muted)", maxWidth: "300px" }}>
        {t("support.body")}
      </p>

      <a
        href={SUPPORT_URL}
        target="_blank"
        rel="noreferrer"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "8px",
          width: "100%",
          maxWidth: "320px",
          minHeight: "48px",
          padding: "12px 20px",
          borderRadius: "var(--r-md)",
          background: "var(--blue)",
          color: "#ffffff",
          fontSize: "16px",
          fontWeight: 600,
          textDecoration: "none",
        }}
      >
        <Send size={18} /> {t("support.cta")}
      </a>
    </div>
  );
}
