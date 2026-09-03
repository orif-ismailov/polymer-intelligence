"use client";

/**
 * Company licences (R5 / P5 — T3.2), shown on the company card.
 *
 * A company uploads its licence through the R1 document flow; staff read it and
 * register it HERE, against a regime. That registration is what the publish gate
 * checks — the document alone says nothing about which of the four regimes it
 * covers, and four different bodies issue them.
 *
 * Revoking takes effect immediately. Nothing is deleted: a withdrawn licence
 * still explains why an offer was public last month.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Ban, Plus } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

type Regime =
  | "precursor_list_iv"
  | "explosive_toxic"
  | "strong_acting"
  | "pkm916_import";

const REGIMES: Regime[] = [
  "precursor_list_iv",
  "explosive_toxic",
  "strong_acting",
  "pkm916_import",
];

interface CompanyLicense {
  id: number;
  regime: Regime;
  category: string | null;
  license_number: string | null;
  issued_by: string | null;
  issued_at: string | null;
  expires_at: string | null;
  status: string;
  revoke_reason: string | null;
  is_active: boolean;
}

export function CompanyLicenses({ companyId }: { companyId: string }) {
  const t = useTranslations("licenses");
  const qc = useQueryClient();
  const { isAdmin } = useAuth();

  const queryKey = ["company-licenses", companyId];
  const { data, isLoading } = useQuery<CompanyLicense[]>({
    queryKey,
    queryFn: () => apiFetch<CompanyLicense[]>(`/admin/companies/${companyId}/licenses`),
  });

  const [open, setOpen] = useState(false);
  const [regime, setRegime] = useState<Regime>("precursor_list_iv");
  const [category, setCategory] = useState("");
  const [number, setNumber] = useState("");
  const [issuedBy, setIssuedBy] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [revoking, setRevoking] = useState<number | null>(null);
  const [reason, setReason] = useState("");

  const register = useMutation({
    mutationFn: () =>
      apiFetch(`/admin/companies/${companyId}/licenses`, {
        method: "POST",
        body: JSON.stringify({
          regime,
          category: category.trim() || null,
          license_number: number.trim() || null,
          issued_by: issuedBy.trim() || null,
          expires_at: expiresAt || null,
        }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey });
      setOpen(false);
      setCategory("");
      setNumber("");
      setIssuedBy("");
      setExpiresAt("");
    },
  });

  const revoke = useMutation({
    mutationFn: (licenseId: number) =>
      apiFetch(`/admin/licenses/${licenseId}/revoke`, {
        method: "POST",
        body: JSON.stringify({ reason: reason.trim() }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey });
      setRevoking(null);
      setReason("");
    },
  });

  return (
    <section className="rounded-lg border border-border bg-background-secondary p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground-muted">
          {t("title")}
        </h2>
        {isAdmin && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-background-tertiary"
          >
            <Plus size={14} aria-hidden="true" /> {t("register")}
          </button>
        )}
      </div>

      <p className="mt-2 text-xs text-foreground-muted">{t("hint")}</p>

      {isLoading && <p className="mt-3 text-sm text-foreground-muted">…</p>}
      {data && data.length === 0 && (
        <p className="mt-3 text-sm text-foreground-muted">{t("empty")}</p>
      )}

      {data && data.length > 0 && (
        <ul className="mt-3 flex flex-col gap-2">
          {data.map((licence) => (
            <li
              key={licence.id}
              className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-background px-3 py-2"
            >
              <BadgeCheck
                size={16}
                aria-hidden="true"
                className={licence.is_active ? "text-accent" : "text-foreground-muted"}
              />
              <span className="text-sm text-foreground">{t(`regime.${licence.regime}`)}</span>
              {licence.category && (
                <span className="text-xs text-foreground-muted">{licence.category}</span>
              )}
              {licence.license_number && (
                <span className="text-xs tabular-nums text-foreground-muted">
                  {licence.license_number}
                </span>
              )}
              <span className="text-xs text-foreground-muted">
                {licence.expires_at ? `${t("until")} ${licence.expires_at}` : t("perpetual")}
              </span>
              <span
                className={`ms-auto rounded-full border px-2 py-0.5 text-xs ${
                  licence.is_active
                    ? "border-accent/40 text-accent"
                    : "border-border text-foreground-muted"
                }`}
              >
                {licence.is_active ? t("active") : t(`status.${licence.status}`)}
              </span>
              {isAdmin && licence.is_active && (
                <button
                  type="button"
                  onClick={() => setRevoking(licence.id)}
                  className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-foreground-muted hover:bg-background-tertiary"
                >
                  <Ban size={14} aria-hidden="true" /> {t("revoke")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {open && isAdmin && (
        <div className="mt-3 grid grid-cols-1 gap-3 rounded-md border border-border bg-background p-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-foreground-muted">{t("fields.regime")}</span>
            <select
              value={regime}
              onChange={(e) => setRegime(e.target.value as Regime)}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
            >
              {REGIMES.map((value) => (
                <option key={value} value={value}>
                  {t(`regime.${value}`)}
                </option>
              ))}
            </select>
          </label>
          <LicenseInput label={t("fields.category")} value={category} onChange={setCategory} />
          <LicenseInput label={t("fields.number")} value={number} onChange={setNumber} />
          <LicenseInput label={t("fields.issuedBy")} value={issuedBy} onChange={setIssuedBy} />
          <label className="flex flex-col gap-1">
            <span className="text-xs text-foreground-muted">{t("fields.expiresAt")}</span>
            <input
              type="date"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
            />
          </label>
          <div className="flex items-end">
            <button
              type="button"
              disabled={register.isPending}
              onClick={() => register.mutate()}
              className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
            >
              {t("save")}
            </button>
          </div>
        </div>
      )}

      {revoking !== null && (
        <div className="mt-3 flex flex-wrap items-end gap-3 rounded-md border border-border bg-background p-3">
          <label className="flex min-w-64 flex-1 flex-col gap-1">
            <span className="text-xs text-foreground-muted">{t("fields.reason")}</span>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
            />
          </label>
          <button
            type="button"
            disabled={revoke.isPending || reason.trim() === ""}
            onClick={() => revoke.mutate(revoking)}
            className="inline-flex items-center gap-2 rounded-md border border-red-500/50 px-4 py-2 text-sm font-medium text-red-400 hover:bg-background-tertiary disabled:opacity-50"
          >
            {t("revoke")}
          </button>
          <button
            type="button"
            onClick={() => {
              setRevoking(null);
              setReason("");
            }}
            className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary"
          >
            {t("cancel")}
          </button>
        </div>
      )}
    </section>
  );
}

function LicenseInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-foreground-muted">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
      />
    </label>
  );
}
