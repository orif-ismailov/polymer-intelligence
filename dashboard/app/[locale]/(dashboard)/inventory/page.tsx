"use client";

/**
 * Inventory (/inventory) — Phase 4. Our own stock (sourcing priority #1).
 * List + quick-add + delete.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, Trash2 } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface InventoryItem {
  id: number;
  product_id: number;
  grade_text: string | null;
  qty_on_hand: number;
  qty_unit: string;
  cost_price: number | null;
  currency: string;
  warehouse_city: string | null;
}

const EMPTY = { product_id: "", grade_text: "", qty_on_hand: "", cost_price: "", warehouse_city: "" };

export default function InventoryPage() {
  const t = useTranslations("broker.inventory");
  const qc = useQueryClient();
  const [form, setForm] = useState({ ...EMPTY });

  const { data, isLoading, isError } = useQuery<InventoryItem[]>({
    queryKey: ["inventory"],
    queryFn: () => apiFetch<InventoryItem[]>("/admin/inventory"),
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["inventory"] });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/admin/inventory", {
        method: "POST",
        body: JSON.stringify({
          product_id: Number(form.product_id),
          grade_text: form.grade_text || null,
          qty_on_hand: Number(form.qty_on_hand),
          cost_price: form.cost_price ? Number(form.cost_price) : null,
          warehouse_city: form.warehouse_city || null,
        }),
      }),
    onSuccess: () => {
      setForm({ ...EMPTY });
      invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => apiFetch(`/admin/inventory/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const valid = form.product_id !== "" && Number(form.qty_on_hand) > 0;
  const input = "rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent";

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <Boxes size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-foreground-muted mt-1">{t("subtitle")}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-2 rounded-lg border border-border bg-background-secondary p-4">
        <input className={input} placeholder={t("product")} value={form.product_id} onChange={(e) => setForm({ ...form, product_id: e.target.value })} type="number" />
        <input className={input} placeholder={t("grade")} value={form.grade_text} onChange={(e) => setForm({ ...form, grade_text: e.target.value })} />
        <input className={input} placeholder={t("qty")} value={form.qty_on_hand} onChange={(e) => setForm({ ...form, qty_on_hand: e.target.value })} type="number" />
        <input className={input} placeholder={t("cost")} value={form.cost_price} onChange={(e) => setForm({ ...form, cost_price: e.target.value })} type="number" />
        <input className={input} placeholder={t("city")} value={form.warehouse_city} onChange={(e) => setForm({ ...form, warehouse_city: e.target.value })} />
        <button type="button" disabled={!valid || create.isPending} onClick={() => create.mutate()} className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50">
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
                <th className="px-4 py-2 text-start font-medium">{t("product")}</th>
                <th className="px-4 py-2 text-start font-medium">{t("grade")}</th>
                <th className="px-4 py-2 text-end font-medium">{t("qty")}</th>
                <th className="px-4 py-2 text-end font-medium">{t("cost")}</th>
                <th className="px-4 py-2 text-start font-medium">{t("city")}</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {data.map((i) => (
                <tr key={i.id} className="border-t border-border">
                  <td className="px-4 py-2 text-foreground">{i.product_id}</td>
                  <td className="px-4 py-2 text-foreground">{i.grade_text ?? "—"}</td>
                  <td className="px-4 py-2 text-end text-foreground">{i.qty_on_hand.toLocaleString()} {i.qty_unit}</td>
                  <td className="px-4 py-2 text-end text-foreground">{i.cost_price == null ? "—" : `${i.cost_price.toLocaleString()} ${i.currency}`}</td>
                  <td className="px-4 py-2 text-foreground">{i.warehouse_city ?? "—"}</td>
                  <td className="px-4 py-2 text-end">
                    <button type="button" onClick={() => remove.mutate(i.id)} className="text-foreground-muted hover:text-red-400" aria-label={t("delete")}>
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
