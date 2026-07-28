"use client";

/**
 * Moderation queue (/moderation)
 *
 * Phase 2 seller marketplace: analyst/admin review of pending seller offers.
 * Approve makes an offer public; reject returns a note to the seller. Backed by
 * GET/POST /api/v1/admin/moderation/offers (require_analyst_or_admin).
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface ComplianceBlock {
  ok: boolean;
  level: "free" | "docs_required" | "license_required" | "prohibited";
  regime: string | null;
  exempt_reason: string | null;
  missing: Array<{ kind: string; detail: string | null }>;
  substance: { id: number; name_ru: string; hs_code: string; cas: string | null } | null;
  /** False while `dangerous_check_enforced` is off — nothing is actually blocked. */
  enforced: boolean;
}

interface ModerationOffer {
  id: number;
  grade_text: string | null;
  product_text: string | null;
  polymer_type: string | null;
  availability: "in_stock" | "on_order";
  qty_available: number | null; // null for «под заказ» (on_order)
  qty_unit: string;
  price: number | null; // null for «под заказ» — shown as "price on request"
  currency: string;
  warehouse_city: string | null;
  created_at: string;
  /** Null for portal-company offers — they have no Telegram seller behind them. */
  seller: {
    company_name: string | null;
    contact_name: string | null;
    phone: string | null;
    telegram_username: string | null;
    is_verified: boolean;
  } | null;
  /** Dual-origin display: "company" | "seller" + the name to show either way. */
  origin: string;
  display_name: string | null;
  company_verified: boolean;
  /** Chemical compliance (P5, FR-C5) — evaluated now, not when submitted. */
  compliance: ComplianceBlock | null;
  /** Laboratory (P6). A passport re-queues the offer so staff see the claim
   *  before buyers do; `lab_verified` means WE arranged the analysis. */
  has_lab_passport: boolean;
  lab_verified: boolean;
}

type T = (key: string, values?: Record<string, string>) => string;

/** Enum values arrive raw from the API; a moderator must not read `precursor_list_iv`. */
const REGIME_KEYS = new Set([
  "precursor_list_iv",
  "explosive_toxic",
  "strong_acting",
  "pkm916_import",
]);
const DOC_KEYS = new Set(["sds", "tds", "coa", "certificate"]);

function regimeLabel(detail: string | null, t: T): string {
  return detail && REGIME_KEYS.has(detail) ? t(`compliance.regime.${detail}`) : (detail ?? "—");
}

function docLabel(detail: string | null, t: T): string {
  return detail && DOC_KEYS.has(detail) ? t(`compliance.docKind.${detail}`) : (detail ?? "—");
}

/** Turn a refused approval into a sentence naming what compliance is waiting for. */
function blockedReason(
  err: unknown,
  t: (key: string, values?: Record<string, string>) => string,
): string {
  const detail = (err as { body?: { detail?: unknown } })?.body?.detail as
    | { code?: string; missing?: Array<{ kind: string; detail: string | null }> }
    | undefined;
  if (detail?.code !== "compliance_blocked") {
    return err instanceof Error ? err.message : t("error");
  }
  const items = (detail.missing ?? []).map((m) =>
    m.kind === "license"
      ? t("compliance.missingLicense", { regime: regimeLabel(m.detail, t) })
      : m.kind === "document"
        ? t("compliance.missingDocument", { doc: docLabel(m.detail, t) })
        : t("compliance.missingProhibited", { act: m.detail ?? "—" }),
  );
  return `${t("compliance.approveBlocked")} ${items.join("; ")}`;
}

export default function ModerationPage() {
  const t = useTranslations("moderation");
  const qc = useQueryClient();
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [blocked, setBlocked] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery<ModerationOffer[]>({
    queryKey: ["moderation-offers"],
    queryFn: () => apiFetch<ModerationOffer[]>("/admin/moderation/offers"),
  });

  const decide = useMutation({
    mutationFn: ({ id, action, note }: { id: number; action: "approve" | "reject"; note?: string }) =>
      apiFetch(`/admin/moderation/offers/${id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ note: note ?? null }),
      }),
    onSuccess: () => {
      setBlocked(null);
      void qc.invalidateQueries({ queryKey: ["moderation-offers"] });
    },
    // A 409 means compliance refused publication (an expired licence, a missing
    // document). Show WHAT is missing — "409 Conflict" tells a moderator nothing.
    onError: (err: unknown) => setBlocked(blockedReason(err, t)),
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <ShieldCheck size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-foreground-muted mt-1">{t("subtitle")}</p>
        </div>
      </div>

      {blocked && (
        <p className="rounded-lg border border-red-500/50 bg-background-secondary p-3 text-sm text-red-400">
          {blocked}
        </p>
      )}

      {isLoading && <p className="text-sm text-foreground-muted">…</p>}
      {isError && <p className="text-sm text-red-400">{t("error")}</p>}
      {data && data.length === 0 && (
        <p className="text-sm text-foreground-muted">{t("empty")}</p>
      )}

      <div className="flex flex-col gap-4">
        {data?.map((o) => (
          <div
            key={o.id}
            className="rounded-lg border border-border bg-background-secondary p-4"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-base font-semibold text-foreground">
                  {o.grade_text || o.product_text || "—"}
                  {o.polymer_type && (
                    <span className="ms-2 text-sm font-normal text-foreground-muted">{o.polymer_type}</span>
                  )}
                </p>
                <p className="text-sm text-foreground-muted mt-1">
                  {o.availability === "on_order" ? t("availOnOrder") : t("availInStock")}
                  {o.qty_available != null ? ` · ${o.qty_available.toLocaleString()} ${o.qty_unit}` : ""}
                  {o.warehouse_city ? ` · ${o.warehouse_city}` : ""}
                </p>
                {/* A portal-company offer has no `seller` block at all — reading
                    through it crashed the whole queue. */}
                <p className="text-sm text-foreground mt-1">
                  {t("seller")}: {o.display_name || o.seller?.company_name || "—"}
                  {o.seller?.phone ? ` · ${o.seller.phone}` : ""}
                  {o.seller?.telegram_username ? ` · @${o.seller.telegram_username}` : ""}
                  {o.company_verified ? ` · ${t("verified")}` : ""}
                </p>
              </div>
              <p className="text-lg font-bold text-accent whitespace-nowrap">
                {o.price != null ? (
                  <>
                    {o.price.toLocaleString()}{" "}
                    <span className="text-xs font-normal text-foreground-muted">
                      {o.currency}/{o.qty_unit}
                    </span>
                  </>
                ) : (
                  <span className="text-sm">{t("priceOnRequest")}</span>
                )}
              </p>
            </div>

            {/* The passport is why this offer came back to the queue (P6), so
                the moderator has to see the claim they are approving. */}
            {o.has_lab_passport && (
              <p className="mt-2 text-sm">
                <span
                  className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                    o.lab_verified
                      ? "bg-amber-100 text-amber-800"
                      : "bg-slate-100 text-slate-700"
                  }`}
                >
                  {t(o.lab_verified ? "lab.verified" : "lab.passport")}
                </span>
              </p>
            )}

            <input
              type="text"
              value={notes[o.id] ?? ""}
              onChange={(e) => setNotes((n) => ({ ...n, [o.id]: e.target.value }))}
              placeholder={t("notePlaceholder")}
              className="mt-3 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent"
            />

            {o.compliance && (o.compliance.substance || !o.compliance.ok) && (
              <div className="mt-3 rounded-md border border-border bg-background p-3">
                <p className="text-xs uppercase tracking-wider text-foreground-muted">
                  {t("compliance.title")}
                </p>
                <p className="mt-1 text-sm text-foreground">
                  {o.compliance.substance
                    ? `${o.compliance.substance.name_ru} · ${o.compliance.substance.hs_code}${
                        o.compliance.substance.cas ? ` · CAS ${o.compliance.substance.cas}` : ""
                      }`
                    : t("compliance.noSubstance")}
                </p>
                <p className="mt-1 text-sm">
                  <span
                    className={
                      o.compliance.ok
                        ? "text-foreground-muted"
                        : o.compliance.enforced
                          ? "text-red-400"
                          : "text-amber-400"
                    }
                  >
                    {t(`compliance.level.${o.compliance.level}`)}
                    {o.compliance.ok
                      ? ` · ${t("compliance.ok")}`
                      : o.compliance.enforced
                        ? ` · ${t("compliance.blocked")}`
                        : ` · ${t("compliance.wouldBlock")}`}
                  </span>
                </p>
                {o.compliance.missing.length > 0 && (
                  <ul className="mt-1 list-disc ps-5 text-sm text-foreground-muted">
                    {o.compliance.missing.map((m, i) => (
                      <li key={`${m.kind}-${m.detail ?? i}`}>
                        {m.kind === "license"
                          ? t("compliance.missingLicense", {
                              regime: regimeLabel(m.detail, t),
                            })
                          : m.kind === "document"
                            ? t("compliance.missingDocument", { doc: docLabel(m.detail, t) })
                            : t("compliance.missingProhibited", { act: m.detail ?? "—" })}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="mt-3 flex gap-2">
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: o.id, action: "approve", note: notes[o.id] })}
                className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
              >
                {t("approve")}
              </button>
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: o.id, action: "reject", note: notes[o.id] })}
                className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary disabled:opacity-50"
              >
                {t("reject")}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
