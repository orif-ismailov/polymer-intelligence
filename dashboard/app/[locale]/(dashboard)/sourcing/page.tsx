"use client";

/**
 * Sourcing (/sourcing) — Phase 4 AI broker. Enter a buyer-request id, run the
 * priority waterfall (inventory → partners → marketplace → import) and show the
 * ranked options + recommended option + market context.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Workflow } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface Option {
  source: string;
  priority: number;
  label: string;
  price: number | null;
  currency: string;
  qty_available: number | null;
  lead_time_days: number | null;
  note: string | null;
}
interface SourcingResult {
  options: Option[];
  recommended: Option | null;
  market: { uz_avg: number | null; cn_avg: number | null };
}
interface SourcingRun {
  id: number;
  request_id: number;
  result: SourcingResult;
}

export default function SourcingPage() {
  const t = useTranslations("broker.sourcing");
  const [reqId, setReqId] = useState("");

  const run = useMutation<SourcingRun, Error, number>({
    mutationFn: (id: number) => apiFetch<SourcingRun>(`/admin/requests/${id}/source`, { method: "POST" }),
  });

  const res = run.data?.result;
  const input = "rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent";

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <Workflow size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-foreground-muted mt-1">{t("subtitle")}</p>
        </div>
      </div>

      <div className="flex items-end gap-2">
        <input className={input} placeholder={t("requestId")} value={reqId} onChange={(e) => setReqId(e.target.value)} type="number" />
        <button
          type="button"
          disabled={reqId === "" || run.isPending}
          onClick={() => run.mutate(Number(reqId))}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
        >
          {t("run")}
        </button>
      </div>

      {run.isError && <p className="text-sm text-red-400">{t("error")}</p>}

      {res && (
        <>
          {res.recommended && (
            <div className="rounded-lg border border-accent/40 bg-accent/10 p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-accent">{t("recommended")}</p>
              <p className="mt-1 text-foreground">
                <span className="font-semibold">{t(`source.${res.recommended.source}`)}</span> · {res.recommended.label} ·{" "}
                {res.recommended.price == null ? "—" : `${res.recommended.price.toLocaleString()} ${res.recommended.currency}`}
              </p>
            </div>
          )}

          <p className="text-sm text-foreground-muted">
            {t("market")}: UZ {res.market.uz_avg?.toLocaleString() ?? "—"} · CN {res.market.cn_avg?.toLocaleString() ?? "—"}
          </p>

          {res.options.length === 0 ? (
            <p className="text-sm text-foreground-muted">{t("empty")}</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="bg-background-secondary text-foreground-muted">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium">{t("source.header")}</th>
                    <th className="px-4 py-2 text-left font-medium">{t("label")}</th>
                    <th className="px-4 py-2 text-right font-medium">{t("price")}</th>
                    <th className="px-4 py-2 text-right font-medium">{t("leadTime")}</th>
                  </tr>
                </thead>
                <tbody>
                  {res.options
                    .slice()
                    .sort((a, b) => a.priority - b.priority)
                    .map((o, idx) => (
                      <tr key={idx} className="border-t border-border">
                        <td className="px-4 py-2 text-foreground">{t(`source.${o.source}`)}</td>
                        <td className="px-4 py-2 text-foreground">{o.label}</td>
                        <td className="px-4 py-2 text-right text-foreground">
                          {o.price == null ? "—" : `${o.price.toLocaleString()} ${o.currency}`}
                        </td>
                        <td className="px-4 py-2 text-right text-foreground">{o.lead_time_days ?? "—"}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
