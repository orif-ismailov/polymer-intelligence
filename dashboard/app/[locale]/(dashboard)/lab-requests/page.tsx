"use client";

/**
 * Lab-request oversight (/lab-requests).
 *
 * Read-only staff view of the buyer→laboratory broadcast board: list with
 * status filter + search, and a detail panel (what's tested, and every
 * laboratory's thread on the request). No mutation, same posture as
 * /contracts and /logistics-requests. NOT the P6 `lab_orders`/`lab_partners`
 * staff-run manual-QC pipeline — this is the buyer↔laboratory-company
 * self-service channel. Backed by GET /api/v1/admin/lab-requests[/{id}]
 * (require_analyst_or_admin).
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { TestTube } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

interface LabRequestRow {
  id: number;
  public_id: string;
  number: string;
  status: string;
  buyer_company_id: number;
  buyer_name: string | null;
  product_id: number | null;
  product_text: string;
  grade_text: string | null;
  study_type: string | null;
  methods: string[];
  sample_qty: string | null;
  comment: string | null;
  purpose: string | null;
  is_urgent: boolean;
  desired_date: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  thread_count: number;
  created_at: string;
  updated_at: string;
}

interface ThreadRow {
  id: number;
  laboratory_company_id: number;
  laboratory_name: string | null;
  message_count: number;
  last_message_at: string | null;
  last_message_preview: string | null;
  created_at: string;
  updated_at: string;
}

interface LabRequestDetail extends LabRequestRow {
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

export default function LabRequestsPage() {
  const t = useTranslations("labRequests");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin-lab-requests", status, q],
    queryFn: () =>
      apiFetch<LabRequestRow[]>(
        `/admin/lab-requests?${new URLSearchParams({ ...(status ? { status } : {}), ...(q ? { q } : {}) }).toString()}`,
      ),
  });

  const detailQuery = useQuery({
    queryKey: ["admin-lab-request", selected],
    queryFn: () => apiFetch<LabRequestDetail>(`/admin/lab-requests/${selected}`),
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
        <TestTube className="h-5 w-5 text-foreground-muted" />
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
                <th className="px-3 py-2">{t("colProduct")}</th>
                <th className="px-3 py-2">{t("colStudyType")}</th>
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
                  <td className="px-3 py-2">
                    {r.product_text}
                    {r.grade_text ? ` · ${r.grade_text}` : ""}
                  </td>
                  <td className="px-3 py-2 text-xs text-foreground-muted">{r.study_type || "—"}</td>
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
                <DetailField
                  label={t("detail.product")}
                  value={detailQuery.data.product_text}
                />
                <DetailField label={t("detail.grade")} value={detailQuery.data.grade_text} />
                <DetailField label={t("detail.studyType")} value={detailQuery.data.study_type} />
                <DetailField
                  label={t("detail.methods")}
                  value={detailQuery.data.methods.length ? detailQuery.data.methods.join(", ") : null}
                  span
                />
                <DetailField label={t("detail.sampleQty")} value={detailQuery.data.sample_qty} />
                <DetailField
                  label={t("detail.urgent")}
                  value={detailQuery.data.is_urgent ? t("detail.urgentYes") : t("detail.urgentNo")}
                />
                <DetailField
                  label={t("detail.desiredDate")}
                  value={detailQuery.data.desired_date}
                />
                <DetailField label={t("detail.purpose")} value={detailQuery.data.purpose} span />
                <DetailField label={t("detail.comment")} value={detailQuery.data.comment} span />
                <DetailField label={t("detail.contactName")} value={detailQuery.data.contact_name} />
                <DetailField label={t("detail.contactEmail")} value={detailQuery.data.contact_email} />
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
                          <span className="font-medium">{th.laboratory_name}</span>
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
