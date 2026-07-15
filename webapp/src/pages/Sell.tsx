/**
 * Продать tab — the seller's own offers + entry to the listing form (IMG_0046 ③).
 *
 * Lists the caller's offers with a moderation-status badge; the primary CTA opens
 * the listing form (/sell/new). Open self-serve: anyone can list; offers go to
 * moderation before appearing in the public catalog.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";

import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import { useProducts } from "../hooks/useProducts";
import type { SellerOfferOut, SellerOfferStatus } from "../types";

const STATUS_CHIP: Record<SellerOfferStatus, string> = {
  draft: "bg-[var(--chip-neutral-bg)] text-[var(--chip-neutral-fg)]",
  pending_moderation: "bg-[var(--chip-warn-bg)] text-[var(--chip-warn-fg)]",
  approved: "bg-[var(--chip-ok-bg)] text-[var(--chip-ok-fg)]",
  rejected: "bg-[var(--chip-down-bg)] text-[var(--chip-down-fg)]",
  archived: "bg-[var(--chip-neutral-bg)] text-[var(--chip-neutral-fg)]",
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

  return (
    <div className="p-4">
      <h1 className="mb-4 text-xl font-bold text-text">{t("sell.myOffers")}</h1>

      <button
        type="button"
        onClick={() => navigate("/sell/new")}
        className="mb-5 block min-h-[48px] w-full cursor-pointer rounded-[var(--r-md)] border-none bg-orange px-5 py-3 text-base font-semibold text-white"
      >
        {t("sell.newOffer")}
      </button>

      {state === "error" && (
        <p className="text-center text-sm text-danger">{t("market.error")}</p>
      )}
      {state === "ok" && offers.length === 0 && (
        <p className="mt-2 text-center text-sm text-text-muted">{t("sell.empty")}</p>
      )}

      {offers.map((o) => (
        <button
          key={o.id}
          type="button"
          onClick={() => navigate(`/sell/${o.id}/edit`)}
          aria-label={`${t("sell.edit")} · ${o.grade_text || o.product_text || ""}`}
          className="mb-3 block w-full cursor-pointer rounded-[var(--r-md)] border border-border bg-surface p-3.5 text-start shadow-[var(--shadow)]"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-[15px] font-semibold text-text">
              {[o.product_id ? products.find((p) => p.id === o.product_id)?.code : null, o.grade_text || o.product_text]
                .filter(Boolean)
                .join(" ") || "—"}
            </span>
            <span className={`rounded-[var(--r-full)] px-2 py-[3px] text-[11px] font-semibold ${STATUS_CHIP[o.status]}`}>
              {t(`offerStatus.${o.status}`)}
            </span>
          </div>
          <div className="mt-1.5 flex items-center justify-between gap-2">
            <span className="text-base font-bold text-green">
              {o.price != null ? (
                <>
                  {o.price.toLocaleString()} <span className="text-xs text-text-muted">{o.currency}/{o.qty_unit}</span>
                </>
              ) : (
                <span className="text-sm">{t("offer.priceOnRequest")}</span>
              )}
            </span>
            <span className="inline-flex items-center gap-1 whitespace-nowrap text-[13px] font-semibold text-text-muted">
              {t("sell.edit")} <ChevronRight size={15} />
            </span>
          </div>
          {o.status === "rejected" && o.moderation_note && (
            <p className="mt-1.5 text-xs text-[var(--chip-down-fg)]">{o.moderation_note}</p>
          )}
        </button>
      ))}
    </div>
  );
}
