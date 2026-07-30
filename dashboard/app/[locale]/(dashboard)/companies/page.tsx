"use client";

/**
 * Companies list (/companies) — R1 W6.
 *
 * The company registry: filter by status and free-text search (name/INN), then
 * drill into a company detail page. Backed by GET /admin/companies?status=&q=
 * (require_analyst_or_admin).
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Building2, Search } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";
import { CompanyStatusBadge } from "@/components/verification/company-status";

// ─── Types ───────────────────────────────────────────────────────────────────

interface CompanyProfile {
  id: number;
  public_id: string;
  jurisdiction: string;
  tax_id: string;
  legal_name: string | null;
  short_name: string | null;
  legal_form: string | null;
  legal_address: string | null;
  director_name: string | null;
  status: string;
  verified_at: string | null;
  reverification_due_at: string | null;
  roles: Array<{ role: string; status: string }>;
}

const COMPANY_STATUS_FILTERS = [
  "draft",
  "pending_verification",
  "verified",
  "rejected",
  "suspended",
  "liquidated",
] as const;

// ─── Page ────────────────────────────────────────────────────────────────────

export default function CompaniesPage() {
  const t = useTranslations("companies");
  const [status, setStatus] = useState<string>("");
  const [queryInput, setQueryInput] = useState("");
  const [q, setQ] = useState("");

  const { data, isLoading, isError } = useQuery<CompanyProfile[]>({
    queryKey: ["companies", status, q],
    queryFn: () => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (q) params.set("q", q);
      const qs = params.toString();
      return apiFetch<CompanyProfile[]>(`/admin/companies${qs ? `?${qs}` : ""}`);
    },
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Building2 size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-foreground-muted mt-1">{t("subtitle")}</p>
        </div>
      </div>

      {/* Search */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setQ(queryInput.trim());
        }}
        className="flex items-center gap-2"
      >
        <div className="relative flex-1 max-w-md">
          <Search
            size={16}
            className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-foreground-muted"
            aria-hidden="true"
          />
          <input
            type="search"
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            placeholder={t("searchPlaceholder")}
            aria-label={t("searchPlaceholder")}
            className="w-full rounded-md border border-border bg-background py-2 pe-3 ps-9 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent"
          />
        </div>
        <button
          type="submit"
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark"
        >
          {t("searchButton")}
        </button>
      </form>

      {/* Status filter */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-foreground-muted">
          {t("filter.label")}
        </span>
        <button
          type="button"
          onClick={() => setStatus("")}
          className={filterBtnCls(status === "")}
        >
          {t("filter.all")}
        </button>
        {COMPANY_STATUS_FILTERS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatus(s)}
            className={filterBtnCls(status === s)}
          >
            {t(`status.${s}`)}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-foreground-muted">{t("loading")}</p>}
      {isError && <p className="text-sm text-red-400">{t("error")}</p>}
      {data && data.length === 0 && (
        <p className="text-sm text-foreground-muted">{t("empty")}</p>
      )}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-tertiary">
              <tr>
                <th className={thCls}>{t("columns.name")}</th>
                <th className={thCls}>{t("columns.inn")}</th>
                <th className={thCls}>{t("columns.jurisdiction")}</th>
                <th className={thCls}>{t("columns.roles")}</th>
                <th className={thCls}>{t("columns.status")}</th>
                <th className={thCls}>{t("columns.verifiedAt")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.map((company) => (
                <tr
                  key={company.id}
                  className="bg-background-secondary hover:bg-background-tertiary transition-colors"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/companies/${company.id}`}
                      className="font-medium text-foreground hover:text-accent"
                    >
                      {company.legal_name || company.short_name || t("unnamed")}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-foreground-muted whitespace-nowrap">
                    {company.tax_id || "—"}
                  </td>
                  <td className="px-4 py-3 text-foreground-muted">
                    {company.jurisdiction || "—"}
                  </td>
                  {/* Confirmed roles only: a declared role is a claim the company
                      made about itself, and staff read this column to check claims. */}
                  <td className="px-4 py-3 text-foreground-muted">
                    {(() => {
                      const confirmed = company.roles.filter((r) => r.status === "confirmed");
                      if (confirmed.length === 0) return "—";
                      return (
                        <span className="flex flex-wrap gap-1">
                          {confirmed.map((r) => (
                            <span
                              key={r.role}
                              className="rounded bg-background-tertiary px-1.5 py-0.5 text-xs"
                            >
                              {t(`roles.${r.role}`)}
                            </span>
                          ))}
                        </span>
                      );
                    })()}
                  </td>
                  <td className="px-4 py-3">
                    <CompanyStatusBadge status={company.status} />
                  </td>
                  <td className="px-4 py-3 text-foreground-muted whitespace-nowrap">
                    {company.verified_at ? (
                      <time dateTime={company.verified_at} title={company.verified_at}>
                        {formatTashkent(company.verified_at)}
                      </time>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Styling helpers ──────────────────────────────────────────────────────────

const thCls =
  "px-4 py-3 text-start text-xs font-semibold text-foreground-muted uppercase tracking-wider";

function filterBtnCls(active: boolean): string {
  return active
    ? "rounded-full border border-accent bg-accent/15 px-3 py-1 text-xs font-medium text-accent"
    : "rounded-full border border-border px-3 py-1 text-xs font-medium text-foreground-muted hover:bg-background-tertiary hover:text-foreground";
}
