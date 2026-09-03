"use client";

/**
 * Deal oversight (/deals) — R4 / P2 T4.2.
 *
 * Staff view of the deals context: list with status/company filters + number
 * search, and a detail panel (parties, timeline, documents, read-only chat).
 *
 * The Trade Room chat is the parties' own record, so there is no way to post
 * into it from here. The one mutation is dispute resolution, and the backend
 * gates it on `require_admin` — the button is hidden for analysts to match,
 * but the server is what enforces it.
 *
 * Backed by GET /api/v1/admin/deals[/{id}[/messages]] and
 * POST /admin/deals/{id}/resolve-dispute.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Handshake } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { formatTashkent } from "@/lib/tz";

interface DealRow {
  id: number;
  public_id: string;
  number: string;
  status: string;
  buyer_company_id: number;
  buyer_name: string | null;
  seller_company_id: number;
  seller_name: string | null;
  amount: string | null;
  currency: string;
  contract_id: number | null;
  cancelled_reason: string | null;
  created_at: string;
  updated_at: string;
}

interface TimelineEntry {
  id: number;
  from_status: string | null;
  to_status: string;
  actor_kind: string;
  actor_id: number | null;
  reason: string | null;
  created_at: string;
}

interface DealDocument {
  id: number;
  kind: string;
  file_name: string;
  size_bytes: number;
  sha256: string;
  uploaded_by_company_id: number;
  revoked: boolean;
  revoked_reason: string | null;
  created_at: string;
}

interface DealDetail extends DealRow {
  timeline: TimelineEntry[];
  documents: DealDocument[];
  message_count: number;
}

interface Message {
  id: number;
  body: string;
  file_name: string | null;
  has_file: boolean;
  author_company_id: number;
  author_company_name: string | null;
  created_at: string;
}

const STATUSES = [
  "",
  "negotiation",
  "contract_pending",
  "contract_signed",
  "payment_pending",
  "paid_escrow",
  "shipped",
  "delivered",
  "completed",
  "cancelled",
  "disputed",
] as const;

/** Statuses a dispute can be restored to — mirrors the server's transition table. */
const RESTORE_TARGETS = ["payment_pending", "paid_escrow", "shipped", "delivered"] as const;

const STATUS_STYLES: Record<string, string> = {
  negotiation: "bg-slate-100 text-slate-700",
  contract_pending: "bg-amber-100 text-amber-800",
  contract_signed: "bg-blue-100 text-blue-800",
  payment_pending: "bg-amber-100 text-amber-800",
  paid_escrow: "bg-green-100 text-green-800",
  shipped: "bg-green-100 text-green-800",
  delivered: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  cancelled: "bg-slate-100 text-slate-500",
  disputed: "bg-red-100 text-red-800",
};

export default function DealsPage() {
  const t = useTranslations("deals");
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();

  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [restoreTo, setRestoreTo] = useState<string>("paid_escrow");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin-deals", status, q],
    queryFn: () =>
      apiFetch<{ items: DealRow[]; total: number }>(
        `/admin/deals?${new URLSearchParams({
          ...(status ? { status } : {}),
          ...(q ? { q } : {}),
        }).toString()}`,
      ),
  });

  const detailQuery = useQuery({
    queryKey: ["admin-deal", selected],
    queryFn: () => apiFetch<DealDetail>(`/admin/deals/${selected}`),
    enabled: selected != null,
  });

  const chatQuery = useQuery({
    queryKey: ["admin-deal-chat", selected],
    queryFn: () => apiFetch<{ items: Message[] }>(`/admin/deals/${selected}/messages`),
    enabled: selected != null,
  });

  const resolve = useMutation({
    mutationFn: (action: "cancel" | "restore") =>
      apiFetch<DealDetail>(`/admin/deals/${selected}/resolve-dispute`, {
        method: "POST",
        body: JSON.stringify({
          action,
          restore_to: action === "restore" ? restoreTo : null,
          comment,
        }),
      }),
    onSuccess: () => {
      setComment("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["admin-deal", selected] });
      void queryClient.invalidateQueries({ queryKey: ["admin-deals"] });
    },
    onError: (err: unknown) => setError(err instanceof Error ? err.message : String(err)),
  });

  const detail = detailQuery.data;

  function statusChip(s: string) {
    return (
      <span
        className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[s] ?? "bg-slate-100"}`}
      >
        {t(`status.${s}`)}
      </span>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center gap-2">
        <Handshake className="h-5 w-5 text-foreground-muted" />
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
        {listQuery.data ? (
          <span className="text-xs text-foreground-muted">
            {t("total", { count: listQuery.data.total })}
          </span>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-secondary text-left text-xs text-foreground-muted">
              <tr>
                <th className="px-3 py-2">{t("colNumber")}</th>
                <th className="px-3 py-2">{t("colParties")}</th>
                <th className="px-3 py-2">{t("colAmount")}</th>
                <th className="px-3 py-2">{t("colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {listQuery.data?.items.map((d) => (
                <tr
                  key={d.id}
                  onClick={() => setSelected(d.id)}
                  className={`cursor-pointer border-t border-border hover:bg-background-tertiary ${
                    selected === d.id ? "bg-background-tertiary" : ""
                  }`}
                >
                  <td className="px-3 py-2 tabular-nums">{d.number}</td>
                  <td className="px-3 py-2 text-xs text-foreground-muted">
                    {d.buyer_name} → {d.seller_name}
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    {d.amount ? `${d.amount} ${d.currency}` : "—"}
                  </td>
                  <td className="px-3 py-2">{statusChip(d.status)}</td>
                </tr>
              ))}
              {listQuery.data?.items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-foreground-muted">
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
          ) : detail ? (
            <div className="space-y-4 text-sm">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold tabular-nums">{detail.number}</h2>
                {statusChip(detail.status)}
              </div>
              <div className="text-foreground-muted">
                {detail.buyer_name} → {detail.seller_name}
                {detail.amount ? ` · ${detail.amount} ${detail.currency}` : ""}
              </div>
              {detail.cancelled_reason ? (
                <p className="text-xs text-red-600">
                  {t("cancelledReason")}: {detail.cancelled_reason}
                </p>
              ) : null}

              {/* Dispute resolution — admin only; the API enforces it too. */}
              {detail.status === "disputed" ? (
                isAdmin ? (
                  <div className="space-y-2 rounded border border-border bg-background-secondary p-3">
                    <h3 className="font-medium">{t("resolve.title")}</h3>
                    <textarea
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      placeholder={t("resolve.comment")}
                      rows={2}
                      className="w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        value={restoreTo}
                        onChange={(e) => setRestoreTo(e.target.value)}
                        className="rounded border border-border bg-background px-2 py-1 text-xs"
                      >
                        {RESTORE_TARGETS.map((s) => (
                          <option key={s} value={s}>
                            {t(`status.${s}`)}
                          </option>
                        ))}
                      </select>
                      <button
                        disabled={!comment.trim() || resolve.isPending}
                        onClick={() => resolve.mutate("restore")}
                        className="rounded border border-border bg-background-tertiary px-3 py-1.5 text-xs font-medium disabled:opacity-50"
                      >
                        {t("resolve.restore")}
                      </button>
                      <button
                        disabled={!comment.trim() || resolve.isPending}
                        onClick={() => resolve.mutate("cancel")}
                        className="rounded border border-red-300 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 disabled:opacity-50"
                      >
                        {t("resolve.cancel")}
                      </button>
                    </div>
                    {error ? <p className="text-xs text-red-600">{error}</p> : null}
                  </div>
                ) : (
                  <p className="rounded border border-border bg-background-secondary p-3 text-xs text-foreground-muted">
                    {t("resolve.adminOnly")}
                  </p>
                )
              ) : null}

              <div>
                <h3 className="mb-1 font-medium">{t("timeline")}</h3>
                <ul className="space-y-1">
                  {detail.timeline.map((e) => (
                    <li key={e.id} className="flex justify-between gap-2 text-xs">
                      <span>
                        {t(`status.${e.to_status}`)}{" "}
                        <span className="text-foreground-muted">({t(`actor.${e.actor_kind}`)})</span>
                        {e.reason ? (
                          <span className="text-foreground-muted"> — {e.reason}</span>
                        ) : null}
                      </span>
                      <span className="shrink-0 text-foreground-muted">
                        {formatTashkent(e.created_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="mb-1 font-medium">{t("documents")}</h3>
                {detail.documents.length === 0 ? (
                  <p className="text-xs text-foreground-muted">{t("noDocuments")}</p>
                ) : (
                  <ul className="space-y-1">
                    {detail.documents.map((d) => (
                      <li key={d.id} className="flex justify-between gap-2 text-xs">
                        <span className={d.revoked ? "text-foreground-muted line-through" : ""}>
                          {d.file_name}{" "}
                          <span className="text-foreground-muted">({t(`docKind.${d.kind}`)})</span>
                        </span>
                        <span className="shrink-0 text-foreground-muted">
                          {formatTashkent(d.created_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <h3 className="mb-1 font-medium">
                  {t("chat")}{" "}
                  <span className="text-xs font-normal text-foreground-muted">
                    ({t("chatReadOnly")})
                  </span>
                </h3>
                {chatQuery.data?.items.length ? (
                  <ul className="max-h-64 space-y-2 overflow-y-auto">
                    {chatQuery.data.items.map((m) => (
                      <li key={m.id} className="rounded border border-border p-2 text-xs">
                        <div className="mb-0.5 flex justify-between gap-2 text-foreground-muted">
                          <span>{m.author_company_name}</span>
                          <span>{formatTashkent(m.created_at)}</span>
                        </div>
                        {m.body ? <p className="whitespace-pre-wrap">{m.body}</p> : null}
                        {m.has_file ? <p className="text-foreground-muted">📎 {m.file_name}</p> : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-foreground-muted">{t("noMessages")}</p>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
