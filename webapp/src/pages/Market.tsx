/**
 * Маркет tab — public seller-offer catalog (IMG_0043 ② / IMG_0046 ①).
 * Phase 1: themed shell with search + category chips and a placeholder. The live
 * catalog (offer cards + product detail) lands with the seller marketplace phase.
 */

import { useEffect, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";

import { backButton, mainButton } from "../telegram";

const CATEGORIES = ["all", "HDPE", "PP", "LDPE", "PVC", "PET"] as const;

export default function Market() {
  const { t } = useTranslation();
  const [active, setActive] = useState<string>("all");

  useEffect(() => {
    backButton.hide();
    mainButton.hide();
  }, []);

  const chip = (selected: boolean): CSSProperties => ({
    flex: "0 0 auto",
    padding: "8px 14px",
    borderRadius: "var(--r-full)",
    border: "1px solid var(--border)",
    background: selected ? "var(--green)" : "var(--surface)",
    color: selected ? "var(--green-on)" : "var(--text-muted)",
    fontSize: "13px",
    fontWeight: 600,
    cursor: "pointer",
  });

  return (
    <div style={{ padding: "16px" }}>
      <h1 style={{ margin: "0 0 16px", fontSize: "20px", fontWeight: 700, color: "var(--text)" }}>
        {t("market.title")}
      </h1>

      <input
        type="search"
        placeholder={t("market.searchPlaceholder")}
        style={{
          width: "100%",
          minHeight: "44px",
          padding: "12px 14px",
          borderRadius: "var(--r-md)",
          border: "1px solid var(--border)",
          background: "var(--surface)",
          color: "var(--text)",
          fontSize: "14px",
          boxSizing: "border-box",
          marginBottom: "12px",
        }}
      />

      <div style={{ display: "flex", gap: "8px", overflowX: "auto", paddingBottom: "4px" }}>
        {CATEGORIES.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setActive(c)}
            style={chip(active === c)}
          >
            {c === "all" ? t("market.all") : c}
          </button>
        ))}
      </div>

      <p style={{ marginTop: "32px", textAlign: "center", fontSize: "14px", color: "var(--text-muted)" }}>
        {t("market.soon")}
      </p>
    </div>
  );
}
