/**
 * C-06 — My Requests screen.
 * Placeholder: full implementation in plan 03-05.
 */
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { styles } from "../App";
import { backButton, mainButton } from "../telegram";
import { useEffect } from "react";

export default function MyRequests() {
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
      <h1 style={styles.headerTitle}>{t("myRequests.title")}</h1>
      <p style={{ ...styles.cardText, marginTop: "16px" }}>{t("myRequests.empty.heading")}</p>
    </div>
  );
}
