/**
 * HowItWorks — the "Как это работает?" explainer (design_2 buyer right panel).
 *
 * Numbered process steps → a green "data is protected" reassurance box → a
 * "Есть вопросы?" prompt that opens the support chat. Full-screen (no tab bar);
 * the Telegram BackButton returns to the previous screen.
 */

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ShieldCheck } from "lucide-react";

import Button from "../components/Button";
import { backButton, mainButton } from "../telegram";

const STEP_KEYS = ["s1", "s2", "s3", "s4"] as const;

export default function HowItWorks() {
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
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "20px 16px" }}>
      <h1 style={{ margin: "0 0 20px", fontSize: "22px", fontWeight: 700 }}>{t("howItWorks.title")}</h1>

      <ol style={{ listStyle: "none", padding: 0, margin: "0 0 24px", display: "flex", flexDirection: "column", gap: "14px" }}>
        {STEP_KEYS.map((k, i) => (
          <li key={k} style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
            <span
              style={{
                flex: "0 0 auto",
                width: "28px",
                height: "28px",
                borderRadius: "var(--r-full)",
                background: "var(--green)",
                color: "var(--green-on)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "13px",
                fontWeight: 700,
              }}
            >
              {i + 1}
            </span>
            <span style={{ fontSize: "15px", lineHeight: 1.45, paddingTop: "3px" }}>{t(`howItWorks.steps.${k}`)}</span>
          </li>
        ))}
      </ol>

      <div
        style={{
          display: "flex",
          gap: "12px",
          alignItems: "flex-start",
          background: "var(--chip-ok-bg)",
          borderRadius: "var(--r-md)",
          padding: "14px",
          marginBottom: "28px",
        }}
      >
        <ShieldCheck size={22} color="var(--chip-ok-fg)" style={{ flex: "0 0 auto" }} aria-hidden="true" />
        <div>
          <p style={{ margin: "0 0 4px", fontSize: "14px", fontWeight: 600, color: "var(--chip-ok-fg)" }}>
            {t("howItWorks.dataProtected.title")}
          </p>
          <p style={{ margin: 0, fontSize: "13px", lineHeight: 1.45, color: "var(--chip-ok-fg)" }}>
            {t("howItWorks.dataProtected.body")}
          </p>
        </div>
      </div>

      <p style={{ margin: "0 0 12px", fontSize: "15px", fontWeight: 600 }}>{t("howItWorks.questions")}</p>
      <Button variant="telegram" onClick={() => navigate("/support")}>
        {t("howItWorks.openChat")}
      </Button>
    </div>
  );
}
