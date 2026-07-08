"use client";

/**
 * Moderation queue (/moderation)
 *
 * Phase 2 seller marketplace: analyst/admin review of pending seller offers.
 * Approve makes an offer public; reject returns a note to the seller. Backed by
 * GET/POST /api/v1/admin/moderation/offers (require_analyst_or_admin).
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface ModerationOffer {
  id: number;
  grade_text: string | null;
  product_text: string | null;
  polymer_type: string | null;
  availability: "in_stock" | "on_order";
  qty_available: number;
  qty_unit: string;
  price: number;
  currency: string;
  warehouse_city: string | null;
  created_at: string;
  seller: {
    company_name: string | null;
    contact_name: string | null;
    phone: string | null;
    telegram_username: string | null;
    is_verified: boolean;
  };
}

export default function ModerationPage() {
  const t = useTranslations("moderation");
  const qc = useQueryClient();
  const [notes, setNotes] = useState<Record<number, string>>({});

  const { data, isLoading, isError } = useQuery<ModerationOffer[]>({
    queryKey: ["moderation-offers"],
    queryFn: () => apiFetch<ModerationOffer[]>("/admin/moderation/offers"),
  });

  const decide = useMutation({
    mutationFn: ({ id, action, note }: { id: number; action: "approve" | "reject"; note?: string }) =>
      apiFetch(`/admin/moderation/offers/${id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ note: note ?? null }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["moderation-offers"] }),
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <ShieldCheck size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-foreground-muted mt-1">{t("subtitle")}</p>
        </div>
      </div>

      {isLoading && <p className="text-sm text-foreground-muted">…</p>}
      {isError && <p className="text-sm text-red-400">{t("error")}</p>}
      {data && data.length === 0 && (
        <p className="text-sm text-foreground-muted">{t("empty")}</p>
      )}

      <div className="flex flex-col gap-4">
        {data?.map((o) => (
          <div
            key={o.id}
            className="rounded-lg border border-border bg-background-secondary p-4"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-base font-semibold text-foreground">
                  {o.grade_text || o.product_text || "—"}
                  {o.polymer_type && (
                    <span className="ml-2 text-sm font-normal text-foreground-muted">{o.polymer_type}</span>
                  )}
                </p>
                <p className="text-sm text-foreground-muted mt-1">
                  {o.availability === "on_order" ? t("availOnOrder") : t("availInStock")}
                  {" · "}
                  {o.qty_available.toLocaleString()} {o.qty_unit}
                  {o.warehouse_city ? ` · ${o.warehouse_city}` : ""}
                </p>
                <p className="text-sm text-foreground mt-1">
                  {t("seller")}: {o.seller.company_name || "—"}
                  {o.seller.phone ? ` · ${o.seller.phone}` : ""}
                  {o.seller.telegram_username ? ` · @${o.seller.telegram_username}` : ""}
                </p>
              </div>
              <p className="text-lg font-bold text-accent whitespace-nowrap">
                {o.price.toLocaleString()}{" "}
                <span className="text-xs font-normal text-foreground-muted">
                  {o.currency}/{o.qty_unit}
                </span>
              </p>
            </div>

            <input
              type="text"
              value={notes[o.id] ?? ""}
              onChange={(e) => setNotes((n) => ({ ...n, [o.id]: e.target.value }))}
              placeholder={t("notePlaceholder")}
              className="mt-3 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent"
            />

            <div className="mt-3 flex gap-2">
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: o.id, action: "approve", note: notes[o.id] })}
                className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
              >
                {t("approve")}
              </button>
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: o.id, action: "reject", note: notes[o.id] })}
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
