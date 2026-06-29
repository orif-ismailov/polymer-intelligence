/**
 * Home — the Главный экран landing (design_2 buyer ① / design.jpeg buyer intro).
 *
 * Brand wordmark, headline, lead, the 1500+/200+/10000+ stat row, the value-prop
 * checklist, and the two domain CTAs: green "Купить сырьё" (→ buyer wizard) and a
 * secondary "Продать сырьё" (→ seller wizard). A "Как это работает?" link opens the
 * explainer (design_2 right panel). Renders inside AppShell so the bottom tabs show.
 *
 * Reconciliation note: the primary CTA is GREEN here (documented "primary CTA = green
 * everywhere"); design.jpeg drew it blue — see docs/design-system.md §Reconciliation.
 */

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Sparkles, CheckCircle2, ShoppingCart, Store, HelpCircle } from "lucide-react";

import Button from "../components/Button";
import { backButton, mainButton } from "../telegram";

const STAT_KEYS = ["buyers", "suppliers", "catalog"] as const;
const BULLET_KEYS = ["verified", "contacts", "prices", "fast"] as const;

export default function Home() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  useEffect(() => {
    backButton.hide();
    mainButton.hide();
  }, []);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: "calc(100vh - 64px - env(safe-area-inset-bottom))",
        padding: "24px 16px 16px",
      }}
    >
      {/* Brand wordmark */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "20px" }}>
        <span
          style={{
            width: "32px",
            height: "32px",
            borderRadius: "var(--r-sm)",
            background: "var(--green)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flex: "0 0 auto",
          }}
        >
          <Sparkles size={18} color="var(--green-on)" />
        </span>
        <span>
          <span style={{ display: "block", fontSize: "17px", fontWeight: 700, color: "var(--text)", lineHeight: 1 }}>
            PetroAI
          </span>
          <span style={{ display: "block", fontSize: "10px", fontWeight: 600, letterSpacing: "0.08em", color: "var(--text-muted)", marginTop: "3px" }}>
            {t("home.brandTag")}
          </span>
        </span>
      </div>

      {/* Headline + lead */}
      <h1 style={{ margin: "0 0 10px", fontSize: "26px", fontWeight: 700, lineHeight: 1.2, color: "var(--text)" }}>
        {t("home.headline")}
      </h1>
      <p style={{ margin: "0 0 20px", fontSize: "15px", lineHeight: 1.5, color: "var(--text-muted)" }}>
        {t("home.lead")}
      </p>

      {/* Stat row */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "20px" }}>
        {STAT_KEYS.map((k) => (
          <div
            key={k}
            style={{
              flex: 1,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--r-md)",
              padding: "12px 8px",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: "18px", fontWeight: 700, color: "var(--green)" }}>{t(`home.stats.${k}.value`)}</div>
            <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "2px" }}>{t(`home.stats.${k}.label`)}</div>
          </div>
        ))}
      </div>

      {/* Value-prop checklist */}
      <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px", display: "flex", flexDirection: "column", gap: "10px" }}>
        {BULLET_KEYS.map((k) => (
          <li key={k} style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
            <CheckCircle2 size={18} color="var(--green)" style={{ flex: "0 0 auto", marginTop: "1px" }} aria-hidden="true" />
            <span style={{ fontSize: "14px", lineHeight: 1.4, color: "var(--text)" }}>{t(`home.bullets.${k}`)}</span>
          </li>
        ))}
      </ul>

      {/* Spacer pushes the CTAs to the bottom of the full-height landing */}
      <div style={{ flex: 1, minHeight: "16px" }} />

      {/* CTAs */}
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        <Button variant="primary" onClick={() => navigate("/request/step/1")}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
            <ShoppingCart size={18} /> {t("home.cta.buy")}
          </span>
        </Button>
        <Button variant="secondary" onClick={() => navigate("/sell")}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
            <Store size={18} /> {t("home.cta.sell")}
          </span>
        </Button>
      </div>

      <button
        type="button"
        onClick={() => navigate("/how-it-works")}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "6px",
          width: "100%",
          marginTop: "16px",
          padding: "10px",
          background: "transparent",
          border: "none",
          color: "var(--blue)",
          fontSize: "14px",
          fontWeight: 600,
          cursor: "pointer",
        }}
      >
        <HelpCircle size={16} /> {t("home.howItWorks")}
      </button>
    </div>
  );
}
