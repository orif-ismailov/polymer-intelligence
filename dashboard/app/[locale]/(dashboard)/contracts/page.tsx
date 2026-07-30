"use client";

/**
 * Contract oversight (/contracts) — R3 Stage B TB3.2.
 *
 * Read-only staff view of the contracts context: list with status filter + search,
 * and a detail panel (parties, signatures, audit timeline, document access). No
 * mutation — dispute tooling is future Deal Lifecycle work. Backed by
 * GET /api/v1/admin/contracts[/{id}] (require_analyst_or_admin).
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

interface ContractRow {
  id: number;
  public_id: string;
  title: string;
  status: string;
  template_code: string | null;
  initiator_name: string | null;
  counterparty_name: string | null;
  created_at: string;
  activated_at: string | null;
  document_available: boolean;
  document_sha256: string | null;
}

interface Signature {
  company_id: number;
  company_name: string | null;
  signed_at: string;
}
interface TimelineEntry {
  action: string;
  at: string;
  details: Record<string, unknown>;
}
interface ContractDetail extends ContractRow {
  variables: Record<string, unknown>;
  declined_reason: string | null;
  signatures: Signature[];
  timeline: TimelineEntry[];
}

const STATUSES = [
  "",
  "draft",
  "pending_counterparty",
  "pending_signatures",
  "active",
  "declined",
  "cancelled",
  "expired",
] as const;

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  pending_counterparty: "bg-amber-100 text-amber-800",
  pending_signatures: "bg-blue-100 text-blue-800",
  active: "bg-green-100 text-green-800",
  declined: "bg-red-100 text-red-800",
  cancelled: "bg-slate-100 text-slate-500",
  expired: "bg-slate-100 text-slate-500",
};

export default function ContractsPage() {
  const t = useTranslations("contracts");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin-contracts", status, q],
    queryFn: () =>
      apiFetch<ContractRow[]>(
        `/admin/contracts?${new URLSearchParams({ ...(status ? { status } : {}), ...(q ? { q } : {}) }).toString()}`,
      ),
  });

  const detailQuery = useQuery({
    queryKey: ["admin-contract", selected],
    queryFn: () => apiFetch<ContractDetail>(`/admin/contracts/${selected}`),
    enabled: selected != null,
  });

  async function openDocument(id: number): Promise<void> {
    const { url } = await apiFetch<{ url: string }>(`/admin/contracts/${id}/document?as=url`);
    window.open(url, "_blank", "noopener");
  }

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
        <FileText className="h-5 w-5 text-foreground-muted" />
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

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-secondary text-left text-xs text-foreground-muted">
              <tr>
                <th className="px-3 py-2">{t("colTitle")}</th>
                <th className="px-3 py-2">{t("colParties")}</th>
                <th className="px-3 py-2">{t("colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {listQuery.data?.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => setSelected(c.id)}
                  className={`cursor-pointer border-t border-border hover:bg-background-tertiary ${
                    selected === c.id ? "bg-background-tertiary" : ""
                  }`}
                >
                  <td className="px-3 py-2">{c.title}</td>
                  <td className="px-3 py-2 text-xs text-foreground-muted">
                    {c.initiator_name} → {c.counterparty_name}
                  </td>
                  <td className="px-3 py-2">{statusChip(c.status)}</td>
                </tr>
              ))}
              {listQuery.data?.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-3 py-6 text-center text-foreground-muted">
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
                <h2 className="font-semibold">{detailQuery.data.title}</h2>
                {statusChip(detailQuery.data.status)}
              </div>
              <div className="text-foreground-muted">
                {detailQuery.data.initiator_name} → {detailQuery.data.counterparty_name}
              </div>
              {detailQuery.data.document_available ? (
                <button
                  onClick={() => void openDocument(detailQuery.data!.id)}
                  className="rounded border border-border bg-background-tertiary px-3 py-1.5 text-xs font-medium text-foreground hover:bg-background-secondary"
                >
                  {t("openDocument")}
                </button>
              ) : null}
              {detailQuery.data.document_sha256 ? (
                <div className="break-all text-xs text-foreground-muted">
                  sha256: {detailQuery.data.document_sha256}
                </div>
              ) : null}

              <div>
                <h3 className="mb-1 font-medium">{t("signatures")}</h3>
                {detailQuery.data.signatures.length === 0 ? (
                  <p className="text-xs text-foreground-muted">{t("noSignatures")}</p>
                ) : (
                  <ul className="space-y-1">
                    {detailQuery.data.signatures.map((s) => (
                      <li key={s.company_id} className="flex justify-between text-xs">
                        <span>{s.company_name}</span>
                        <span className="text-foreground-muted">{formatTashkent(s.signed_at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <h3 className="mb-1 font-medium">{t("timeline")}</h3>
                <ul className="space-y-1">
                  {detailQuery.data.timeline.map((e, i) => (
                    <li key={i} className="flex justify-between text-xs">
                      <span className="text-foreground-muted">{e.action}</span>
                      <span className="text-foreground-muted">{formatTashkent(e.at)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
