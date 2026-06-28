"use client";

/**
 * Market intelligence (/intel) — Phase 4 board.
 * Per-product buyers/sellers, average seller price vs buyer target, and the spread.
 */

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface IntelRow {
  code: string;
  buyers: number;
  sellers: number;
  avg_seller_price: number | null;
  avg_buyer_target: number | null;
  spread: number | null;
}

function fmt(n: number | null): string {
  return n == null ? "—" : n.toLocaleString();
}

export default function IntelPage() {
  const t = useTranslations("broker.intel");
  const { data, isLoading, isError } = useQuery<IntelRow[]>({
    queryKey: ["intel-market"],
    queryFn: () => apiFetch<IntelRow[]>("/admin/intel/market"),
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <BarChart3 size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-foreground-muted mt-1">{t("subtitle")}</p>
        </div>
      </div>

      {isLoading && <p className="text-sm text-foreground-muted">…</p>}
      {isError && <p className="text-sm text-red-400">{t("error")}</p>}
      {data && data.length === 0 && <p className="text-sm text-foreground-muted">{t("empty")}</p>}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-secondary text-foreground-muted">
              <tr>
                <th className="px-4 py-2 text-left font-medium">{t("product")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("buyers")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("sellers")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("avgSeller")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("avgBuyer")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("spread")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.code} className="border-t border-border">
                  <td className="px-4 py-2 font-medium text-foreground">{r.code}</td>
                  <td className="px-4 py-2 text-right text-foreground">{r.buyers}</td>
                  <td className="px-4 py-2 text-right text-foreground">{r.sellers}</td>
                  <td className="px-4 py-2 text-right text-foreground">{fmt(r.avg_seller_price)}</td>
                  <td className="px-4 py-2 text-right text-foreground">{fmt(r.avg_buyer_target)}</td>
                  <td className="px-4 py-2 text-right font-semibold text-accent">{fmt(r.spread)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
