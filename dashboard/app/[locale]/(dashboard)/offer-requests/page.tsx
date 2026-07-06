"use client";

/**
 * Offer-request review queue (/offer-requests)
 *
 * The buyer "Request an offer" brokerage flow: analyst/admin review of pending
 * inquiries. Approve forwards the inquiry to the seller by bot DM (buyer contact
 * withheld); reject closes it. Backed by GET/POST /api/v1/admin/offer-requests
 * (require_analyst_or_admin). Staff see BOTH parties' contacts here.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface OfferBrief {
  id: number;
  product_text: string | null;
  grade_text: string | null;
  price: number;
  currency: string;
  qty_unit: string;
}

interface OfferRequest {
  id: number;
  status: string;
  quantity: number | null;
  qty_unit: string;
  target_price: number | null;
  currency: string | null;
  message: string | null;
  created_at: string;
  offer: OfferBrief;
  buyer: {
    contact_name: string | null;
    company_name: string | null;
    phone: string | null;
    telegram_user_id: number | null;
  };
  seller: {
    company_name: string | null;
    phone: string | null;
    telegram_username: string | null;
  };
}

export default function OfferRequestsPage() {
  const t = useTranslations("offerRequests");
  const qc = useQueryClient();
  const [notes, setNotes] = useState<Record<number, string>>({});

  const { data, isLoading, isError } = useQuery<OfferRequest[]>({
    queryKey: ["offer-requests"],
    queryFn: () => apiFetch<OfferRequest[]>("/admin/offer-requests"),
  });

  const decide = useMutation({
    mutationFn: ({ id, action, note }: { id: number; action: "approve" | "reject"; note?: string }) =>
      apiFetch(`/admin/offer-requests/${id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ note: note ?? null }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["offer-requests"] }),
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <Inbox size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-foreground-muted mt-1">{t("subtitle")}</p>
        </div>
      </div>

      {isLoading && <p className="text-sm text-foreground-muted">…</p>}
      {isError && <p className="text-sm text-red-400">{t("error")}</p>}
      {data && data.length === 0 && <p className="text-sm text-foreground-muted">{t("empty")}</p>}

      <div className="flex flex-col gap-4">
        {data?.map((r) => (
          <div key={r.id} className="rounded-lg border border-border bg-background-secondary p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-base font-semibold text-foreground">
                  {r.offer.grade_text || r.offer.product_text || "—"}
                </p>
                <p className="text-sm text-foreground-muted mt-1">
                  {t("listedPrice")}: {r.offer.price.toLocaleString()} {r.offer.currency}/{r.offer.qty_unit}
                </p>
                <p className="text-sm text-foreground mt-1">
                  {r.quantity != null && (
                    <>
                      {t("wantsQty")}: {r.quantity.toLocaleString()} {r.qty_unit}
                    </>
                  )}
                  {r.target_price != null && (
                    <span className="ml-2">
                      · {t("targetPrice")}: {r.target_price.toLocaleString()} {r.currency || r.offer.currency}
                    </span>
                  )}
                </p>
                {r.message && <p className="text-sm text-foreground mt-1 italic">“{r.message}”</p>}
              </div>
            </div>

            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <div className="rounded-md border border-border bg-background p-3">
                <p className="text-xs font-medium uppercase text-foreground-muted">{t("buyer")}</p>
                <p className="text-sm text-foreground mt-1">
                  {r.buyer.company_name || "—"}
                  {r.buyer.contact_name ? ` · ${r.buyer.contact_name}` : ""}
                </p>
                <p className="text-sm text-foreground-muted">
                  {r.buyer.phone || ""}
                  {r.buyer.telegram_user_id ? ` · id ${r.buyer.telegram_user_id}` : ""}
                </p>
              </div>
              <div className="rounded-md border border-border bg-background p-3">
                <p className="text-xs font-medium uppercase text-foreground-muted">{t("seller")}</p>
                <p className="text-sm text-foreground mt-1">{r.seller.company_name || "—"}</p>
                <p className="text-sm text-foreground-muted">
                  {r.seller.phone || ""}
                  {r.seller.telegram_username ? ` · @${r.seller.telegram_username}` : ""}
                </p>
              </div>
            </div>

            <input
              type="text"
              value={notes[r.id] ?? ""}
              onChange={(e) => setNotes((n) => ({ ...n, [r.id]: e.target.value }))}
              placeholder={t("notePlaceholder")}
              className="mt-3 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent"
            />

            <div className="mt-3 flex gap-2">
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: r.id, action: "approve", note: notes[r.id] })}
                className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
              >
                {t("approve")}
              </button>
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: r.id, action: "reject", note: notes[r.id] })}
                className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary disabled:opacity-50"
              >
                {t("reject")}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
