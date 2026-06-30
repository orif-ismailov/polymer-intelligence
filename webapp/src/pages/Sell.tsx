/**
 * Продать tab — the seller's own offers + entry to the listing form (IMG_0046 ③).
 *
 * Lists the caller's offers with a moderation-status badge; the primary CTA opens
 * the listing form (/sell/new). Open self-serve: anyone can list; offers go to
 * moderation before appearing in the public catalog.
 */

import { useEffect, useState, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import { useProducts } from "../hooks/useProducts";
import type { SellerOfferOut, SellerOfferStatus } from "../types";

const STATUS_CHIP: Record<SellerOfferStatus, { bg: string; fg: string }> = {
  draft: { bg: "var(--chip-neutral-bg)", fg: "var(--chip-neutral-fg)" },
  pending_moderation: { bg: "var(--chip-warn-bg)", fg: "var(--chip-warn-fg)" },
  approved: { bg: "var(--chip-ok-bg)", fg: "var(--chip-ok-fg)" },
  rejected: { bg: "var(--chip-down-bg)", fg: "var(--chip-down-fg)" },
  archived: { bg: "var(--chip-neutral-bg)", fg: "var(--chip-neutral-fg)" },
};

export default function Sell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { products } = useProducts();
  const [offers, setOffers] = useState<SellerOfferOut[]>([]);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    backButton.hide();
    mainButton.hide();
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .getMyOffers()
      .then((data) => {
        if (!cancelled) {
          setOffers(data);
          setState("ok");
        }
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const badge = (status: SellerOfferStatus): CSSProperties => ({
    fontSize: "11px",
    fontWeight: 600,
    padding: "3px 8px",
    borderRadius: "var(--r-full)",
    background: STATUS_CHIP[status].bg,
    color: STATUS_CHIP[status].fg,
  });

  return (
    <div style={{ padding: "16px" }}>
      <h1 style={{ margin: "0 0 16px", fontSize: "20px", fontWeight: 700, color: "var(--text)" }}>
        {t("sell.myOffers")}
      </h1>

      <button
        type="button"
        onClick={() => navigate("/sell/new")}
        style={{
          display: "block",
          width: "100%",
          minHeight: "48px",
          padding: "12px 20px",
          borderRadius: "var(--r-md)",
          background: "var(--orange)",
          color: "#ffffff",
          border: "none",
          fontSize: "16px",
          fontWeight: 600,
          cursor: "pointer",
          marginBottom: "20px",
        }}
      >
        {t("sell.newOffer")}
      </button>

      {state === "error" && (
        <p style={{ textAlign: "center", color: "var(--danger)", fontSize: "14px" }}>{t("market.error")}</p>
      )}
      {state === "ok" && offers.length === 0 && (
        <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "14px", marginTop: "8px" }}>
          {t("sell.empty")}
        </p>
      )}

      {offers.map((o) => (
        <div
          key={o.id}
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-md)",
            boxShadow: "var(--shadow)",
            padding: "14px",
            marginBottom: "12px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "15px", fontWeight: 600, color: "var(--text)" }}>
              {[o.product_id ? products.find((p) => p.id === o.product_id)?.code : null, o.grade_text || o.product_text]
                .filter(Boolean)
                .join(" ") || "—"}
            </span>
            <span style={badge(o.status)}>{t(`offerStatus.${o.status}`)}</span>
          </div>
          <div style={{ fontSize: "16px", fontWeight: 700, color: "var(--green)", marginTop: "6px" }}>
            {o.price.toLocaleString()} <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>{o.currency}/{o.qty_unit}</span>
          </div>
          {o.status === "rejected" && o.moderation_note && (
            <p style={{ fontSize: "12px", color: "var(--chip-down-fg)", marginTop: "6px" }}>{o.moderation_note}</p>
          )}
        </div>
      ))}
    </div>
  );
}
