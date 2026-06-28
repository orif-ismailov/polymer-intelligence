/**
 * Продать tab — seller listing entry (IMG_0043/0044 bottom, IMG_0046 ③).
 * Phase 1: themed placeholder. The 5-step seller wizard + moderation land with the
 * seller marketplace phase.
 */

import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { backButton, mainButton } from "../telegram";

export default function Sell() {
  const { t } = useTranslation();

  useEffect(() => {
    backButton.hide();
    mainButton.hide();
  }, []);

  return (
    <div style={{ padding: "16px" }}>
      <h1 style={{ margin: "0 0 16px", fontSize: "20px", fontWeight: 700, color: "var(--text)" }}>
        {t("sell.title")}
      </h1>
      <p style={{ marginTop: "24px", textAlign: "center", fontSize: "14px", color: "var(--text-muted)" }}>
        {t("sell.soon")}
      </p>
    </div>
  );
}
