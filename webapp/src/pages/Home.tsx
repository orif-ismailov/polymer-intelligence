/**
 * C-01 — Home screen.
 *
 * The "Оставить заявку" CTA is the dominant accent element on this screen
 * (the only accent fill — UI-SPEC §Color reserved-for list).
 * No blocking API call on mount (first-paint ≤3 s budget, REQ-nfr-performance).
 * BackButton is hidden on this screen.
 * MainButton is hidden on this screen.
 */

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2, Zap, Star } from "lucide-react";
import { backButton, mainButton } from "../telegram";

const styles = {
  container: {
    minHeight: "100vh",
    backgroundColor: "var(--tg-theme-bg-color, #1e293b)",
    color: "var(--tg-theme-text-color, #f8fafc)",
    padding: "0",
  },
  hero: {
    padding: "48px 16px 32px",
    textAlign: "center" as const,
  },
  heading: {
    margin: "0 0 12px",
    fontSize: "18px",
    fontWeight: 600,
    color: "var(--tg-theme-text-color, #f8fafc)",
  },
  subheading: {
    margin: "0 0 32px",
    fontSize: "14px",
    color: "var(--tg-theme-hint-color, #94a3b8)",
    lineHeight: 1.5,
  },
  accentButton: {
    display: "block",
    width: "100%",
    minHeight: "44px",
    padding: "12px 20px",
    borderRadius: "8px",
    backgroundColor: "var(--tg-theme-button-color, #10b981)",
    color: "var(--tg-theme-button-text-color, #ffffff)",
    border: "none",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    boxSizing: "border-box" as const,
    marginBottom: "12px",
  },
  secondaryButton: {
    display: "block",
    width: "100%",
    minHeight: "44px",
    padding: "12px 20px",
    borderRadius: "8px",
    backgroundColor: "transparent",
    color: "var(--tg-theme-link-color, #38bdf8)",
    border: "1px solid var(--tg-theme-secondary-bg-color, #334155)",
    fontSize: "14px",
    fontWeight: 400,
    cursor: "pointer",
    boxSizing: "border-box" as const,
  },
  props: {
    padding: "0 16px 32px",
    display: "flex",
    flexDirection: "column" as const,
    gap: "8px",
  },
  propItem: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "12px 16px",
    borderRadius: "12px",
    backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
  },
  propText: {
    fontSize: "14px",
    color: "var(--tg-theme-text-color, #f8fafc)",
    margin: 0,
  },
} as const;

export default function Home() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  useEffect(() => {
    // Hide BackButton and MainButton on Home screen
    backButton.hide();
    mainButton.hide();
  }, []);

  return (
    <div style={styles.container}>
      <div style={styles.hero}>
        <h1 style={styles.heading}>{t("home.heading")}</h1>
        <p style={styles.subheading}>{t("home.subheading")}</p>

        {/* Primary CTA — the focal point, accent fill */}
        <button
          type="button"
          style={styles.accentButton}
          onClick={() => navigate("/request/step/1")}
        >
          {t("home.cta.submit")}
        </button>

        {/* Secondary CTA */}
        <button
          type="button"
          style={styles.secondaryButton}
          onClick={() => navigate("/requests")}
        >
          {t("home.cta.myRequests")}
        </button>
      </div>

      {/* Value props */}
      <div style={styles.props}>
        <div style={styles.propItem}>
          <Zap
            size={20}
            color="var(--tg-theme-button-color, #10b981)"
            aria-hidden="true"
          />
          <p style={styles.propText}>{t("home.prop.fast")}</p>
        </div>
        <div style={styles.propItem}>
          <Star
            size={20}
            color="var(--tg-theme-button-color, #10b981)"
            aria-hidden="true"
          />
          <p style={styles.propText}>{t("home.prop.convenient")}</p>
        </div>
        <div style={styles.propItem}>
          <CheckCircle2
            size={20}
            color="var(--tg-theme-button-color, #10b981)"
            aria-hidden="true"
          />
          <p style={styles.propText}>{t("home.prop.reliable")}</p>
        </div>
      </div>
    </div>
  );
}
