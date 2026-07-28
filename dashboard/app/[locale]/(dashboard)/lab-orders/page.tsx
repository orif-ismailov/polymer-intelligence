"use client";

/**
 * Laboratory queue (/lab-orders) — R5 / P6 T5.2.
 *
 * The analysis is a MANUAL process: a partner laboratory runs it, over the
 * phone, on its own schedule. This page is where an operator lives that
 * process — pick a request up, agree it with a lab, wait for the sample, wait
 * for the result, upload the passport.
 *
 * Two things it deliberately does not do:
 *
 *   * re-derive the state machine. The buttons come from the server's
 *     `available_transitions`, so the UI can never offer a move the API refuses;
 *   * offer `done` as a plain status. Finishing an order means producing the
 *     passport, so that button opens the upload instead.
 *
 * The queue is OLDEST first — everything else in the dashboard is newest-first,
 * but a work list is read from the bottom of the pile.
 *
 * Backed by GET /api/v1/admin/lab-orders and its transition/result routes.
 */

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { ApiError, apiFetch, apiUpload } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

interface LabOrder {
  id: number;
  number: string;
  status: string;
  company_id: number;
  company_name: string | null;
  offer_id: number | null;
  offer_title: string | null;
  deal_id: number | null;
  substance_id: number | null;
  substance_name: string | null;
  sample_volume: string | null;
  comment: string | null;
  lab_partner_id: number | null;
  lab_partner_name: string | null;
  operator_note: string | null;
  rejected_reason: string | null;
  result_offer_file_id: number | null;
  result_deal_document_id: number | null;
  handled_by: number | null;
  available_transitions: string[];
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

interface LabOrderList {
  items: LabOrder[];
  counters: { submitted: number; in_progress: number; done: number; rejected: number };
}

interface LabPartner {
  id: number;
  name: string;
  contacts: Record<string, string>;
  company_id: number | null;
  note: string | null;
  is_active: boolean;
  created_at: string;
}

const STATUSES = ["", "submitted", "accepted", "sample_awaited", "in_analysis", "done", "rejected"] as const;

const STATUS_STYLES: Record<string, string> = {
  submitted: "bg-slate-100 text-slate-700",
  accepted: "bg-blue-100 text-blue-800",
  sample_awaited: "bg-amber-100 text-amber-800",
  in_analysis: "bg-blue-100 text-blue-800",
  done: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
};

/** Moves that need an explanation before the API will take them. */
const NEEDS_REASON = new Set(["rejected"]);

export default function LabOrdersPage() {
  const t = useTranslations("labOrders");
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin-lab-orders", status],
    queryFn: () =>
      apiFetch<LabOrderList>(`/admin/lab-orders${status ? `?status=${status}` : ""}`),
  });
  const partnersQuery = useQuery({
    queryKey: ["admin-lab-partners", "active"],
    queryFn: () => apiFetch<LabPartner[]>("/admin/lab-partners?active_only=true"),
  });

  function refresh(): void {
    setNote("");
    setError(null);
    void queryClient.invalidateQueries({ queryKey: ["admin-lab-orders"] });
  }

  const transition = useMutation({
    mutationFn: (toStatus: string) =>
      apiFetch<LabOrder>(`/admin/lab-orders/${selected}/transition`, {
        method: "POST",
        body: JSON.stringify({ to_status: toStatus, note: note.trim() || null }),
      }),
    onSuccess: refresh,
    onError: (err: unknown) => setError(reasonOf(err)),
  });

  const assign = useMutation({
    mutationFn: (partnerId: number) =>
      apiFetch<LabOrder>(`/admin/lab-orders/${selected}/partner`, {
        method: "POST",
        body: JSON.stringify({ lab_partner_id: partnerId }),
      }),
    onSuccess: refresh,
    onError: (err: unknown) => setError(reasonOf(err)),
  });

  const uploadResult = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      if (note.trim()) form.append("note", note.trim());
      return apiUpload<LabOrder>(`/admin/lab-orders/${selected}/result`, form);
    },
    onSuccess: refresh,
    onError: (err: unknown) => setError(reasonOf(err)),
  });

  /**
   * The API answers a refusal with a specific code — "that transition is not
   * allowed", "a rejection needs a reason", "`done` needs the passport". A bare
   * 409 tells an operator holding a PDF nothing about what to do next.
   */
  function reasonOf(err: unknown): string {
    const detail =
      err instanceof ApiError && err.body && typeof err.body === "object"
        ? (err.body as { detail?: unknown }).detail
        : null;
    if (typeof detail === "string" && t.has(`errors.${detail}`)) {
      return t(`errors.${detail}`);
    }
    return err instanceof Error ? err.message : String(err);
  }

  const data = listQuery.data;
  const current = data?.items.find((o) => o.id === selected) ?? null;

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
        <FlaskConical className="h-5 w-5 text-foreground-muted" />
        <h1 className="text-xl font-semibold">{t("title")}</h1>
      </div>
      <p className="mb-4 text-sm text-foreground-muted">{t("subtitle")}</p>

      {data ? (
        <div className="mb-4 flex flex-wrap gap-3">
          <Counter label={t("counters.submitted")} value={data.counters.submitted} />
          <Counter label={t("counters.inProgress")} value={data.counters.in_progress} />
          <Counter label={t("counters.done")} value={data.counters.done} />
          <Counter label={t("counters.rejected")} value={data.counters.rejected} />
        </div>
      ) : null}

      <div className="mb-4">
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
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-secondary text-left text-xs text-foreground-muted">
              <tr>
                <th className="px-3 py-2">{t("colNumber")}</th>
                <th className="px-3 py-2">{t("colCompany")}</th>
                <th className="px-3 py-2">{t("colSubject")}</th>
                <th className="px-3 py-2">{t("colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((order) => (
                <tr
                  key={order.id}
                  onClick={() => {
                    setSelected(order.id);
                    setNote("");
                    setError(null);
                  }}
                  className={`cursor-pointer border-t border-border hover:bg-background-tertiary ${
                    selected === order.id ? "bg-background-tertiary" : ""
                  }`}
                >
                  <td className="px-3 py-2 tabular-nums">{order.number}</td>
                  <td className="px-3 py-2 text-xs text-foreground-muted">
                    {order.company_name ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-xs text-foreground-muted">
                    {order.offer_title ??
                      (order.deal_id ? t("subjectDeal", { id: order.deal_id }) : "—")}
                  </td>
                  <td className="px-3 py-2">{statusChip(order.status)}</td>
                </tr>
              ))}
              {data?.items.length === 0 ? (
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
          {current == null ? (
            <p className="text-sm text-foreground-muted">{t("selectHint")}</p>
          ) : (
            <div className="space-y-4 text-sm">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold tabular-nums">{current.number}</h2>
                {statusChip(current.status)}
              </div>

              <dl className="space-y-1 text-xs text-foreground-muted">
                <Row label={t("company")} value={current.company_name ?? "—"} />
                <Row
                  label={t("subject")}
                  value={
                    current.offer_title ??
                    (current.deal_id ? t("subjectDeal", { id: current.deal_id }) : "—")
                  }
                />
                {current.substance_name ? (
                  <Row label={t("substance")} value={current.substance_name} />
                ) : null}
                {current.sample_volume ? (
                  <Row label={t("volume")} value={current.sample_volume} />
                ) : null}
                <Row label={t("createdAt")} value={formatTashkent(current.created_at)} />
                {current.completed_at ? (
                  <Row label={t("completedAt")} value={formatTashkent(current.completed_at)} />
                ) : null}
                {current.rejected_reason ? (
                  <Row label={t("rejectedReason")} value={current.rejected_reason} />
                ) : null}
                {current.operator_note ? (
                  <Row label={t("operatorNote")} value={current.operator_note} />
                ) : null}
              </dl>

              {current.comment ? (
                <p className="rounded border border-border bg-background-secondary p-3 text-xs">
                  {current.comment}
                </p>
              ) : null}

              {/* Which laboratory is doing the work. Not a status change — an
                  order can be assigned and re-assigned at any live stage. */}
              <div className="space-y-1">
                <label className="text-xs text-foreground-muted">{t("partner")}</label>
                <select
                  value={current.lab_partner_id ?? ""}
                  onChange={(e) => {
                    if (e.target.value) assign.mutate(Number(e.target.value));
                  }}
                  disabled={assign.isPending}
                  className="w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                >
                  <option value="">{t("partnerNone")}</option>
                  {partnersQuery.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              {current.available_transitions.length === 0 ? (
                <p className="rounded border border-border bg-background-secondary p-3 text-xs text-foreground-muted">
                  {t("terminal")}
                </p>
              ) : (
                <div className="space-y-2 rounded border border-border bg-background-secondary p-3">
                  <h3 className="font-medium">{t("act.title")}</h3>
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder={t("act.note")}
                    rows={2}
                    className="w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    {current.available_transitions.map((target) =>
                      target === "done" ? (
                        // `done` is not a status you can just set: it needs the
                        // passport, so the button opens the file picker.
                        <button
                          key={target}
                          disabled={uploadResult.isPending}
                          onClick={() => fileRef.current?.click()}
                          className="rounded border border-green-500/50 bg-background-tertiary px-3 py-1.5 text-xs font-medium disabled:opacity-50"
                        >
                          {t("act.uploadResult")}
                        </button>
                      ) : (
                        <button
                          key={target}
                          disabled={
                            transition.isPending ||
                            (NEEDS_REASON.has(target) && !note.trim())
                          }
                          onClick={() => transition.mutate(target)}
                          className={`rounded border px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${
                            NEEDS_REASON.has(target)
                              ? "border-red-300 bg-red-50 text-red-700"
                              : "border-border bg-background-tertiary"
                          }`}
                        >
                          {t(`act.${target}`)}
                        </button>
                      ),
                    )}
                  </div>
                  <p className="text-xs text-foreground-muted">{t("act.reasonHint")}</p>
                  <input
                    ref={fileRef}
                    type="file"
                    accept="application/pdf"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) uploadResult.mutate(file);
                      e.target.value = "";
                    }}
                  />
                  {error ? <p className="text-xs text-red-500">{error}</p> : null}
                </div>
              )}

              {current.result_offer_file_id || current.result_deal_document_id ? (
                <p className="rounded border border-green-500/50 bg-background-secondary p-3 text-xs text-foreground-muted">
                  {t("resultAttached")}
                </p>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Counter({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border px-4 py-2">
      <p className="text-xs text-foreground-muted">{label}</p>
      <p className="text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt>{label}</dt>
      <dd className="text-right text-foreground">{value}</dd>
    </div>
  );
}
