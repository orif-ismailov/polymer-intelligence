/**
 * Маркет tab — public seller-offer catalog (IMG_0043 ② / IMG_0046 ①).
 *
 * Fetches approved offers from /webapp/market/offers, filterable by category chip
 * and free-text search. Tapping a card opens the offer detail (/market/:id).
 */

import { useEffect, useState, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MapPin, BadgeCheck, Phone, Send } from "lucide-react";

import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import { useProducts } from "../hooks/useProducts";
import type { CatalogOffer } from "../types";

export default function Market() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { products } = useProducts();
  const categories: { code: string; id: number | null }[] = [
    { code: "all", id: null },
    ...products.map((p) => ({ code: p.code, id: p.id })),
  ];
  const [active, setActive] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [offers, setOffers] = useState<CatalogOffer[]>([]);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    backButton.hide();
    mainButton.hide();
  }, []);

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    const product_id = active === "all" ? undefined : products.find((p) => p.code === active)?.id;
    api
      .getCatalogOffers({ product_id, q: query.trim() || undefined })
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
  }, [active, query, products]);

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
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("market.searchPlaceholder")}
        style={{
          width: "100%",
          minHeight: "44px",
          padding: "12px 14px",
          borderRadius: "var(--r-md)",
          border: "1px solid var(--border)",
          background: "var(--surface)",
          color: "var(--text)",
          fontSize: "16px",
          boxSizing: "border-box",
          marginBottom: "12px",
        }}
      />

      <div style={{ display: "flex", gap: "8px", overflowX: "auto", paddingBottom: "4px", marginBottom: "16px" }}>
        {categories.map((c) => (
          <button key={c.code} type="button" onClick={() => setActive(c.code)} style={chip(active === c.code)}>
            {c.code === "all" ? t("market.all") : c.code}
          </button>
        ))}
      </div>

      {state === "loading" && (
        <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "14px" }}>…</p>
      )}
      {state === "error" && (
        <p style={{ textAlign: "center", color: "var(--danger)", fontSize: "14px" }}>{t("market.error")}</p>
      )}
      {state === "ok" && offers.length === 0 && (
        <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "14px", marginTop: "24px" }}>
          {t("market.empty")}
        </p>
      )}

      {state === "ok" && offers.length > 0 && (
        <h2 style={{ margin: "0 0 12px", fontSize: "15px", fontWeight: 600, color: "var(--text)" }}>
          {t("market.popular")}
        </h2>
      )}

      {state === "ok" &&
        offers.map((o) => {
          const img = o.files?.find((f) => f.kind === "image");
          return (
            <button
              key={o.id}
              type="button"
              onClick={() => navigate(`/market/${o.id}`)}
              style={{
                display: "flex",
                gap: "12px",
                width: "100%",
                textAlign: "left",
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "var(--r-md)",
                boxShadow: "var(--shadow)",
                padding: "14px",
                marginBottom: "12px",
                cursor: "pointer",
                color: "var(--text)",
              }}
            >
              {img ? (
                <img
                  src={api.offerImageUrl(o.id, img.id)}
                  alt=""
                  style={{ width: "64px", height: "64px", flex: "0 0 auto", borderRadius: "var(--r-sm)", objectFit: "cover", background: "var(--surface-2)" }}
                />
              ) : (
                <span style={{ width: "64px", height: "64px", flex: "0 0 auto", borderRadius: "var(--r-sm)", background: "var(--surface-2)" }} />
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                  <div>
                    <div style={{ fontSize: "15px", fontWeight: 600 }}>{o.grade_text || o.product_text || "—"}</div>
                    {o.polymer_type && (
                      <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>{o.polymer_type}</div>
                    )}
                  </div>
                  <div style={{ fontSize: "18px", fontWeight: 700, color: "var(--green)", whiteSpace: "nowrap" }}>
                    {o.price.toLocaleString()} <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>{o.currency}/{o.qty_unit}</span>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "10px", marginTop: "8px", fontSize: "12px", color: "var(--text-muted)" }}>
                  <span>{o.qty_available.toLocaleString()} {o.qty_unit}</span>
                  {o.warehouse_city && (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "3px" }}>
                      <MapPin size={13} /> {o.warehouse_city}
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "8px" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "13px", color: "var(--text)" }}>
                    {o.seller.company_name || t("offer.seller")}
                    {o.seller.is_verified && <BadgeCheck size={14} color="var(--green)" />}
                  </span>
                  <span style={{ display: "inline-flex", gap: "10px", color: "var(--text-muted)" }}>
                    {o.seller.phone && <Phone size={16} color="var(--green)" />}
                    {o.seller.telegram_username && <Send size={16} color="var(--blue)" />}
                  </span>
                </div>
              </div>
            </button>
          );
        })}
    </div>
  );
}
