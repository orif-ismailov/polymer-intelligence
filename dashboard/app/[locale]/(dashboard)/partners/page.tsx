"use client";

/**
 * Partner suppliers (/partners) — Phase 4. Known partners (sourcing priority #2).
 * List + quick-add + delete.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Handshake, Trash2 } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface Partner {
  id: number;
  name: string;
  product_id: number | null;
  indicative_price: number | null;
  currency: string;
  lead_time_days: number | null;
}

const EMPTY = { name: "", product_id: "", indicative_price: "", lead_time_days: "" };

export default function PartnersPage() {
  const t = useTranslations("broker.partners");
  const qc = useQueryClient();
  const [form, setForm] = useState({ ...EMPTY });

  const { data, isLoading, isError } = useQuery<Partner[]>({
    queryKey: ["partners"],
    queryFn: () => apiFetch<Partner[]>("/admin/partners"),
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["partners"] });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/admin/partners", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          product_id: form.product_id ? Number(form.product_id) : null,
          indicative_price: form.indicative_price ? Number(form.indicative_price) : null,
          lead_time_days: form.lead_time_days ? Number(form.lead_time_days) : null,
        }),
      }),
    onSuccess: () => {
      setForm({ ...EMPTY });
      invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => apiFetch(`/admin/partners/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const input = "rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent";

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <Handshake size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-foreground-muted mt-1">{t("subtitle")}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-2 rounded-lg border border-border bg-background-secondary p-4">
        <input className={input} placeholder={t("name")} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className={input} placeholder={t("product")} value={form.product_id} onChange={(e) => setForm({ ...form, product_id: e.target.value })} type="number" />
        <input className={input} placeholder={t("price")} value={form.indicative_price} onChange={(e) => setForm({ ...form, indicative_price: e.target.value })} type="number" />
        <input className={input} placeholder={t("lead")} value={form.lead_time_days} onChange={(e) => setForm({ ...form, lead_time_days: e.target.value })} type="number" />
        <button type="button" disabled={form.name.trim() === "" || create.isPending} onClick={() => create.mutate()} className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50">
          {t("add")}
        </button>
      </div>

      {isLoading && <p className="text-sm text-foreground-muted">…</p>}
      {isError && <p className="text-sm text-red-400">{t("error")}</p>}
      {data && data.length === 0 && <p className="text-sm text-foreground-muted">{t("empty")}</p>}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-secondary text-foreground-muted">
              <tr>
                <th className="px-4 py-2 text-left font-medium">{t("name")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("product")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("price")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("lead")}</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id} className="border-t border-border">
                  <td className="px-4 py-2 font-medium text-foreground">{p.name}</td>
                  <td className="px-4 py-2 text-right text-foreground">{p.product_id ?? "—"}</td>
                  <td className="px-4 py-2 text-right text-foreground">{p.indicative_price == null ? "—" : `${p.indicative_price.toLocaleString()} ${p.currency}`}</td>
                  <td className="px-4 py-2 text-right text-foreground">{p.lead_time_days ?? "—"}</td>
                  <td className="px-4 py-2 text-right">
                    <button type="button" onClick={() => remove.mutate(p.id)} className="text-foreground-muted hover:text-red-400" aria-label={t("delete")}>
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
