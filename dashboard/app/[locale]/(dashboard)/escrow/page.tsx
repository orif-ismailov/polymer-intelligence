"use client";

/**
 * Escrow operations (/escrow) — R4 / P3 T2.3.
 *
 * The operator's day in two queues: who owes us money (pending) and who we owe
 * money to (funded). Plus the deals nobody else would surface — signed but not
 * invoiceable, because no total was ever agreed.
 *
 * Marking money is the most consequential button in the product, so it is
 * guarded three ways: the backend requires `require_admin` (analysts see a
 * read-only queue), a comment is mandatory, and a confirmation checkbox has to
 * be ticked — which the API also enforces, so a UI-only tick would not do.
 *
 * The buttons come from the server's `available_marks`, so this page never
 * re-derives the escrow state machine.
 *
 * Backed by GET /api/v1/admin/escrow and POST /admin/escrow/{id}/mark.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Banknote } from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { formatTashkent } from "@/lib/tz";

interface EscrowPayment {
  id: number;
  deal_id: number;
  deal_number: string;
  deal_status: string;
  status: string;
  mode: string;
  amount: string;
  currency: string;
  buyer_name: string | null;
  seller_name: string | null;
  funded_at: string | null;
  released_at: string | null;
  refunded_at: string | null;
  note: string | null;
  provider_ref: string | null;
  available_marks: string[];
  created_at: string;
  updated_at: string;
}

interface BlockedDeal {
  deal_id: number;
  deal_number: string;
  buyer_name: string | null;
  seller_name: string | null;
  reason: string;
  created_at: string;
}

interface EscrowList {
  items: EscrowPayment[];
  blocked: BlockedDeal[];
  counters: {
    awaiting_funds: number;
    awaiting_payout: number;
    settled: number;
    blocked: number;
    provider_holds: number;
  };
}

/**
 * A bank callback that was recorded and deliberately NOT applied (R6 / P7.b).
 * `claimed_status` is the bank's word, `payment_status` is our ledger — the row
 * exists because they disagree. There is no resolve button: settling the
 * disagreement IS the ordinary mark on the payment, after which the hold stops
 * matching and drops off the list by itself.
 */
interface ProviderHold {
  event_id: number;
  provider: string;
  external_id: string;
  reason: string;
  detail: string;
  claimed_status: string | null;
  payment_id: number | null;
  payment_status: string | null;
  deal_id: number | null;
  created_at: string;
}

const STATUSES = ["", "pending", "funded", "released", "refunded"] as const;

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800",
  funded: "bg-blue-100 text-blue-800",
  released: "bg-green-100 text-green-800",
  refunded: "bg-slate-100 text-slate-500",
};

export default function EscrowPage() {
  const t = useTranslations("escrow");
  // The deal's own status is named in the deals namespace — reuse it rather than
  // translating the same ten statuses twice, or showing the raw enum value.
  const tDeal = useTranslations("deals");
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();

  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin-escrow", status],
    queryFn: () =>
      apiFetch<EscrowList>(`/admin/escrow${status ? `?status=${status}` : ""}`),
  });

  // Only fetched when the counters say there is something to fetch: the common
  // case is zero holds, and an empty panel is not worth a second request.
  const holdsQuery = useQuery({
    queryKey: ["admin-escrow-holds"],
    queryFn: () => apiFetch<{ items: ProviderHold[] }>("/admin/escrow/provider-events"),
    enabled: (listQuery.data?.counters.provider_holds ?? 0) > 0,
  });

  const mark = useMutation({
    mutationFn: (toStatus: string) =>
      apiFetch<EscrowPayment>(`/admin/escrow/${selected}/mark`, {
        method: "POST",
        body: JSON.stringify({ to_status: toStatus, note, confirmed }),
      }),
    onSuccess: () => {
      // Reset the guards after every mark: the next payment deserves its own
      // deliberate tick, not one inherited from the last click.
      setNote("");
      setConfirmed(false);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["admin-escrow"] });
      // A mark is how a provider hold gets resolved, so the queue has to be
      // re-read — the row it settled should disappear.
      void queryClient.invalidateQueries({ queryKey: ["admin-escrow-holds"] });
    },
    onError: (err: unknown) => setError(reasonOf(err)),
  });

  /**
   * The API answers a refused mark with a specific reason — "you cannot release
   * before the buyer confirms delivery", "this refund needs the deal disputed
   * first". A bare "409 Conflict" tells an operator holding a bank statement
   * nothing about what to do next, so translate the reason when we recognise it.
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
  const current = data?.items.find((p) => p.id === selected) ?? null;

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
        <Banknote className="h-5 w-5 text-foreground-muted" />
        <h1 className="text-xl font-semibold">{t("title")}</h1>
      </div>
      <p className="mb-4 text-sm text-foreground-muted">{t("subtitle")}</p>

      {data ? (
        <div className="mb-4 flex flex-wrap gap-3">
          <Counter label={t("counters.awaitingFunds")} value={data.counters.awaiting_funds} />
          <Counter label={t("counters.awaitingPayout")} value={data.counters.awaiting_payout} />
          <Counter label={t("counters.settled")} value={data.counters.settled} />
          <Counter label={t("counters.blocked")} value={data.counters.blocked} />
          <Counter label={t("counters.providerHolds")} value={data.counters.provider_holds} />
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
                <th className="px-3 py-2">{t("colDeal")}</th>
                <th className="px-3 py-2">{t("colParties")}</th>
                <th className="px-3 py-2">{t("colAmount")}</th>
                <th className="px-3 py-2">{t("colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => {
                    setSelected(p.id);
                    setConfirmed(false);
                    setError(null);
                  }}
                  className={`cursor-pointer border-t border-border hover:bg-background-tertiary ${
                    selected === p.id ? "bg-background-tertiary" : ""
                  }`}
                >
                  <td className="px-3 py-2 tabular-nums">{p.deal_number}</td>
                  <td className="px-3 py-2 text-xs text-foreground-muted">
                    {p.buyer_name} → {p.seller_name}
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    {p.amount} {p.currency}
                  </td>
                  <td className="px-3 py-2">{statusChip(p.status)}</td>
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
                <h2 className="font-semibold tabular-nums">{current.deal_number}</h2>
                {statusChip(current.status)}
              </div>
              <div className="text-foreground-muted">
                {current.buyer_name} → {current.seller_name}
              </div>
              <p className="text-lg font-semibold tabular-nums">
                {current.amount} {current.currency}
              </p>
              <dl className="space-y-1 text-xs text-foreground-muted">
                <Row label={t("dealStatus")} value={tDeal(`status.${current.deal_status}`)} />
                <Row label={t("mode")} value={t(`modeValue.${current.mode}`)} />
                {current.funded_at ? (
                  <Row label={t("fundedAt")} value={formatTashkent(current.funded_at)} />
                ) : null}
                {current.released_at ? (
                  <Row label={t("releasedAt")} value={formatTashkent(current.released_at)} />
                ) : null}
                {current.refunded_at ? (
                  <Row label={t("refundedAt")} value={formatTashkent(current.refunded_at)} />
                ) : null}
                {current.note ? <Row label={t("lastNote")} value={current.note} /> : null}
              </dl>

              {current.available_marks.length === 0 ? (
                <p className="rounded border border-border bg-background-secondary p-3 text-xs text-foreground-muted">
                  {t("terminal")}
                </p>
              ) : isAdmin ? (
                <div className="space-y-2 rounded border border-border bg-background-secondary p-3">
                  <h3 className="font-medium">{t("mark.title")}</h3>
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder={t("mark.note")}
                    rows={2}
                    className="w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                  />
                  <label className="flex items-start gap-2 text-xs text-foreground-muted">
                    <input
                      type="checkbox"
                      checked={confirmed}
                      onChange={(e) => setConfirmed(e.target.checked)}
                      className="mt-0.5"
                    />
                    <span>{t("mark.confirm")}</span>
                  </label>
                  <div className="flex flex-wrap items-center gap-2">
                    {current.available_marks.map((target) => (
                      <button
                        key={target}
                        disabled={!note.trim() || !confirmed || mark.isPending}
                        onClick={() => mark.mutate(target)}
                        className={`rounded border px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${
                          target === "refunded"
                            ? "border-red-300 bg-red-50 text-red-700"
                            : "border-border bg-background-tertiary"
                        }`}
                      >
                        {t(`mark.${target}`)}
                      </button>
                    ))}
                  </div>
                  {error ? <p className="text-xs text-red-600">{error}</p> : null}
                </div>
              ) : (
                <p className="rounded border border-border bg-background-secondary p-3 text-xs text-foreground-muted">
                  {t("mark.adminOnly")}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Signed deals with no escrow. The outbox consumer only logs these, so
          without this list they would sit invisible at contract_signed. */}
      {data?.blocked.length ? (
        /* Amber border, not an amber FILL: the dashboard theme is dark, and a
           light amber panel washes the muted body text out to unreadable. */
        <div className="mt-6 rounded-lg border border-amber-500/50 bg-background-secondary p-4">
          <h2 className="mb-1 font-medium">{t("blocked.title")}</h2>
          <p className="mb-2 text-xs text-foreground-muted">{t("blocked.hint")}</p>
          <ul className="space-y-1">
            {data.blocked.map((b) => (
              <li key={b.deal_id} className="flex flex-wrap justify-between gap-2 text-xs">
                <span className="tabular-nums">{b.deal_number}</span>
                <span className="text-foreground-muted">
                  {b.buyer_name} → {b.seller_name}
                </span>
                <span className="text-amber-400">{t(`blocked.reason.${b.reason}`)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Bank callbacks we understood and refused to apply unattended. A refund
          kills a deal, and an early release pays a seller for goods nobody
          confirmed arrived — both need a person. Resolving one is the ordinary
          mark above, after which the row stops disagreeing and disappears. */}
      {holdsQuery.data?.items.length ? (
        <div className="mt-6 rounded-lg border border-red-500/50 bg-background-secondary p-4">
          <h2 className="mb-1 font-medium">{t("providerHolds.title")}</h2>
          <p className="mb-2 text-xs text-foreground-muted">{t("providerHolds.hint")}</p>
          <ul className="space-y-2">
            {holdsQuery.data.items.map((h) => (
              <li
                key={h.event_id}
                className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2 text-xs first:border-0 first:pt-0"
              >
                <span className="text-foreground-muted">
                  {h.provider} · {formatTashkent(h.created_at)}
                </span>
                <span>
                  {h.claimed_status
                    ? t("providerHolds.disagreement", {
                        bank: t(`status.${h.claimed_status}`),
                        ours: h.payment_status ? t(`status.${h.payment_status}`) : "—",
                      })
                    : t("providerHolds.unreadable")}
                </span>
                <span className="text-red-400">
                  {t.has(`providerHolds.reason.${h.reason}`)
                    ? t(`providerHolds.reason.${h.reason}`)
                    : h.reason}
                </span>
                {h.payment_id ? (
                  <button
                    onClick={() => {
                      setSelected(h.payment_id);
                      setConfirmed(false);
                      setError(null);
                    }}
                    className="rounded border border-border bg-background-tertiary px-2 py-1 font-medium"
                  >
                    {t("providerHolds.open")}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
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
