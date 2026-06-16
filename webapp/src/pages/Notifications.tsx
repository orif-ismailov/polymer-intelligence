/**
 * C-08 — Notifications screen ("Уведомления").
 *
 * In Phase 3, notification persistence is bot-side only. This screen
 * exists as a deep-link target and nav destination (UI-SPEC C-08).
 * Renders EmptyState since no notification data is available client-side.
 *
 * BackButton → Home (/).
 */

import { useEffect, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { styles } from "../App";
import { backButton, mainButton } from "../telegram";
import EmptyState from "../components/EmptyState";

export default function Notifications() {
  const { t } = useTranslation();
  const navigate = useNavigate();

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

  return (
    <div style={{ ...styles.app }}>
      {/* Screen header */}
      <div style={styles.header as CSSProperties}>
        <h1 style={styles.headerTitle}>{t("notifications.title")}</h1>
      </div>

      <div style={{ padding: "16px" }}>
        <EmptyState
          heading={t("notifications.empty.heading")}
          body={t("notifications.empty.body")}
        />
      </div>
    </div>
  );
}
