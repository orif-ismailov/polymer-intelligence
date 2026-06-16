/**
 * C-08 — Notifications screen.
 * Placeholder: full implementation in plan 03-05.
 */
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { styles } from "../App";
import { backButton, mainButton } from "../telegram";
import { useEffect } from "react";

export default function Notifications() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  useEffect(() => {
    backButton.show();
    const cleanup = backButton.onClick(() => navigate("/"));
    mainButton.hide();
    return () => { cleanup(); backButton.hide(); };
  }, [navigate]);

  return (
    <div style={{ ...styles.app, padding: "16px" }}>
      <h1 style={styles.headerTitle}>{t("notifications.title")}</h1>
      <p style={{ ...styles.cardText, marginTop: "16px" }}>{t("notifications.empty.heading")}</p>
      <p style={{ ...styles.cardText, marginTop: "8px" }}>{t("notifications.empty.body")}</p>
    </div>
  );
}
