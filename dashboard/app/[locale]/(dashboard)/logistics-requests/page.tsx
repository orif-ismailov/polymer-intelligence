"use client";

/**
 * Logistics-request oversight (/logistics-requests).
 *
 * Read-only staff view of the buyer→carrier broadcast board: list with status
 * filter + search, and a detail panel (cargo, route, and every carrier's
 * thread on the request). No mutation — these are peer-to-peer portal flows
 * with no inherent need for staff moderation, same posture as /contracts.
 * Backed by GET /api/v1/admin/logistics-requests[/{id}] (require_analyst_or_admin).
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Truck } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

interface LogisticsRequestRow {
  id: number;
  public_id: string;
  number: string;
  status: string;
  buyer_company_id: number;
  buyer_name: string | null;
  cargo_name: string;
  volume: string;
  volume_unit: string;
  packaging_type: string | null;
  special_requirements: string | null;
  from_country: string;
  from_city: string | null;
  to_country: string;
  to_city: string | null;
  contact_phone: string | null;
  thread_count: number;
  created_at: string;
  updated_at: string;
}

interface ThreadRow {
  id: number;
  carrier_company_id: number;
  carrier_name: string | null;
  message_count: number;
  last_message_at: string | null;
  last_message_preview: string | null;
  created_at: string;
  updated_at: string;
}

interface LogisticsRequestDetail extends LogisticsRequestRow {
  threads: ThreadRow[];
}

const STATUSES = ["", "submitted", "viewed", "in_progress", "quoted", "closed", "rejected"] as const;

const STATUS_STYLES: Record<string, string> = {
  submitted: "bg-blue-100 text-blue-800",
  viewed: "bg-slate-100 text-slate-700",
  in_progress: "bg-amber-100 text-amber-800",
  quoted: "bg-violet-100 text-violet-800",
  closed: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
};

function route(r: { from_country: string; from_city: string | null; to_country: string; to_city: string | null }): string {
  const from = r.from_city ? `${r.from_country}, ${r.from_city}` : r.from_country;
  const to = r.to_city ? `${r.to_country}, ${r.to_city}` : r.to_country;
  return `${from} → ${to}`;
}

export default function LogisticsRequestsPage() {
  const t = useTranslations("logisticsRequests");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin-logistics-requests", status, q],
    queryFn: () =>
      apiFetch<LogisticsRequestRow[]>(
        `/admin/logistics-requests?${new URLSearchParams({ ...(status ? { status } : {}), ...(q ? { q } : {}) }).toString()}`,
      ),
  });

  const detailQuery = useQuery({
    queryKey: ["admin-logistics-request", selected],
    queryFn: () => apiFetch<LogisticsRequestDetail>(`/admin/logistics-requests/${selected}`),
    enabled: selected != null,
  });

  function statusChip(s: string) {
    return (
      <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[s] ?? "bg-slate-100"}`}>
        {t(`status.${s}`)}
      </span>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center gap-2">
        <Truck className="h-5 w-5 text-foreground-muted" />
        <h1 className="text-xl font-semibold">{t("title")}</h1>
      </div>
      <p className="mb-4 text-sm text-foreground-muted">{t("subtitle")}</p>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s ? t(`status.${s}`) : t("filterAll")}
            </option>
          ))}
        </select>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("search")}
          className="rounded border border-border bg-background px-2 py-1 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-1 focus:ring-accent"
        />
      </div>

      {listQuery.isLoading && <p className="text-sm text-foreground-muted">{t("loading")}</p>}
      {listQuery.isError && <p className="text-sm text-red-400">{t("error")}</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-secondary text-left text-xs text-foreground-muted">
              <tr>
                <th className="px-3 py-2">{t("colNumber")}</th>
                <th className="px-3 py-2">{t("colRoute")}</th>
                <th className="px-3 py-2">{t("colCargo")}</th>
                <th className="px-3 py-2">{t("colBuyer")}</th>
                <th className="px-3 py-2">{t("colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {listQuery.data?.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setSelected(r.id)}
                  className={`cursor-pointer border-t border-border hover:bg-background-tertiary ${
                    selected === r.id ? "bg-background-tertiary" : ""
                  }`}
                >
                  <td className="px-3 py-2">{r.number}</td>
                  <td className="px-3 py-2 text-xs text-foreground-muted">{route(r)}</td>
                  <td className="px-3 py-2">{r.cargo_name}</td>
                  <td className="px-3 py-2 text-xs text-foreground-muted">{r.buyer_name}</td>
                  <td className="px-3 py-2">{statusChip(r.status)}</td>
                </tr>
              ))}
              {listQuery.data?.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-foreground-muted">
                    {t("empty")}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="rounded-lg border border-border p-4">
          {selected == null ? (
            <p className="text-sm text-foreground-muted">{t("selectHint")}</p>
          ) : detailQuery.isLoading ? (
            <p className="text-sm text-foreground-muted">…</p>
          ) : detailQuery.data ? (
            <div className="space-y-4 text-sm">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold">{detailQuery.data.number}</h2>
                {statusChip(detailQuery.data.status)}
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                <DetailField label={t("detail.buyer")} value={detailQuery.data.buyer_name} />
                <DetailField label={t("detail.cargo")} value={detailQuery.data.cargo_name} />
                <DetailField
                  label={t("detail.volume")}
                  value={`${detailQuery.data.volume} ${detailQuery.data.volume_unit}`}
                />
                <DetailField label={t("detail.packaging")} value={detailQuery.data.packaging_type} />
                <DetailField label={t("detail.route")} value={route(detailQuery.data)} span />
                <DetailField
                  label={t("detail.specialRequirements")}
                  value={detailQuery.data.special_requirements}
                  span
                />
                <DetailField label={t("detail.contactPhone")} value={detailQuery.data.contact_phone} />
                <DetailField
                  label={t("detail.createdAt")}
                  value={formatTashkent(detailQuery.data.created_at)}
                />
                <DetailField
                  label={t("detail.updatedAt")}
                  value={formatTashkent(detailQuery.data.updated_at)}
                />
              </dl>

              <div>
                <h3 className="mb-1 font-medium">{t("threads.title")}</h3>
                {detailQuery.data.threads.length === 0 ? (
                  <p className="text-xs text-foreground-muted">{t("threads.empty")}</p>
                ) : (
                  <ul className="space-y-2">
                    {detailQuery.data.threads.map((th) => (
                      <li key={th.id} className="rounded border border-border p-2 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{th.carrier_name}</span>
                          <span className="text-foreground-muted">
                            {t("threads.messageCount")}: {th.message_count}
                          </span>
                        </div>
                        {th.last_message_preview && (
                          <p className="mt-1 text-foreground-muted">{th.last_message_preview}</p>
                        )}
                        <p className="mt-1 text-foreground-muted">
                          {t("threads.lastMessage")}:{" "}
                          {th.last_message_at ? formatTashkent(th.last_message_at) : t("threads.never")}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function DetailField({
  label,
  value,
  span,
}: {
  label: string;
  value: string | null;
  span?: boolean;
}) {
  return (
    <div className={span ? "col-span-2" : undefined}>
      <dt className="text-foreground-muted">{label}</dt>
      <dd className="mt-0.5 break-words">{value || "—"}</dd>
    </div>
  );
}
