/**
 * Мои запросы предложений — the buyer's "Request an offer" inquiries.
 *
 * Lists the buyer's OfferRequest inquiries with their moderation status. Tapping one
 * opens the detail/edit screen (/inquiries/:id) where the buyer can revise it; editing
 * an approved inquiry re-enters review and notifies the seller of the changes.
 *
 * BackButton → Маркет.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import type { OfferRequestOut, OfferRequestStatus } from "../types";

const STATUS_COLOR: Record<OfferRequestStatus, string> = {
  pending: "text-orange",
  approved: "text-green",
  rejected: "text-danger",
};

export default function MyInquiries() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [items, setItems] = useState<OfferRequestOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchItems = useCallback(async () => {
    setError(null);
    try {
      setItems(await api.getMyOfferRequests());
    } catch {
      setError(t("error.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchItems();
  }, [fetchItems]);

  useEffect(() => {
    backButton.show();
    const cleanup = backButton.onClick(() => navigate("/market"));
    mainButton.hide();
    return () => {
      cleanup();
      backButton.hide();
    };
  }, [navigate]);

  return (
    <div className="p-4">
      <h1 className="mb-4 text-xl font-bold text-text">{t("inquiries.title")}</h1>

      {error && <ErrorBanner message={error} />}
      {loading && <p className="text-sm text-text-muted">…</p>}

      {!loading && !error && items.length === 0 && (
        <EmptyState
          heading={t("inquiries.empty.heading")}
          body={t("inquiries.empty.body")}
          cta={t("inquiries.empty.cta")}
          onCta={() => navigate("/market")}
        />
      )}

      {!loading &&
        !error &&
        items.map((it) => {
          const title = it.offer.grade_text || it.offer.product_text || "—";
          const cur = it.currency ?? it.offer.currency;
          return (
            <button
              key={it.id}
              type="button"
              onClick={() => navigate(`/inquiries/${it.id}`)}
              className="mb-3 flex w-full items-start justify-between gap-3 rounded-[var(--r-md)] border border-border bg-surface p-3.5 text-start text-text shadow-[var(--shadow)]"
            >
              <div className="min-w-0">
                <div className="truncate text-[15px] font-semibold">{title}</div>
                <div className="mt-1 text-xs text-text-muted">
                  {it.quantity != null ? `${it.quantity.toLocaleString()} ${it.qty_unit}` : ""}
                  {it.target_price != null ? ` · ${it.target_price.toLocaleString()} ${cur}` : ""}
                </div>
              </div>
              <div className="flex flex-none flex-col items-end gap-1">
                <span className={`text-xs font-semibold ${STATUS_COLOR[it.status]}`}>{t(`inquiries.status.${it.status}`)}</span>
                {it.edited_at && <span className="text-[11px] text-text-muted">{t("inquiries.edited")}</span>}
              </div>
            </button>
          );
        })}
    </div>
  );
}
