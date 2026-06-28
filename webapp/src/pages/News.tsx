/**
 * Новости tab — daily AI market reports (IMG_0046 ④).
 * Phase 1: themed placeholder. The report feed lands with the news-engine phase.
 */

import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { backButton, mainButton } from "../telegram";

export default function News() {
  const { t } = useTranslation();

  useEffect(() => {
    backButton.hide();
    mainButton.hide();
  }, []);

  return (
    <div style={{ padding: "16px" }}>
      <h1 style={{ margin: "0 0 16px", fontSize: "20px", fontWeight: 700, color: "var(--text)" }}>
        {t("news.title")}
      </h1>
      <p style={{ marginTop: "24px", textAlign: "center", fontSize: "14px", color: "var(--text-muted)" }}>
        {t("news.soon")}
      </p>
    </div>
  );
}
