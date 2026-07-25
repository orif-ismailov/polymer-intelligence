"use client";

/**
 * Verification queue (/verification) — R1 W6.
 *
 * Analyst/admin review of company-verification cases. Lists cases from
 * GET /admin/verification/cases (optionally ?status=), each row showing the
 * declared company, case type, and per-check status chips. Rows link to the
 * case detail page (/verification/[id]). Backed by require_analyst_or_admin.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { BadgeCheck } from "lucide-react";
import { Link, useRouter } from "@/i18n/navigation";
import { apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";
import {
  CaseStatusBadge,
  CaseTypeLabel,
  CheckChip,
} from "@/components/verification/chips";

// ─── Types ───────────────────────────────────────────────────────────────────

interface VerificationCaseListItem {
  id: number;
  company_id: number;
  company_tax_id: string | null;
  company_name: string | null;
  case_type: string;
  status: string;
  submitted_at: string | null;
  /** check_type → status */
  checks: Record<string, string>;
}

// Case status values the filter offers (excludes draft/cancelled — those aren't
// actionable in the queue but are still styled if the backend returns them).
const CASE_STATUS_FILTERS = [
  "submitted",
  "checks_running",
  "needs_info",
  "pending_review",
  "approved",
  "rejected",
] as const;

// ─── Page ────────────────────────────────────────────────────────────────────

export default function VerificationQueuePage() {
  const t = useTranslations("verification");
  const router = useRouter();
  const [status, setStatus] = useState<string>("");

  const { data, isLoading, isError } = useQuery<VerificationCaseListItem[]>({
    queryKey: ["verification-cases", status],
    queryFn: () =>
      apiFetch<VerificationCaseListItem[]>(
        `/admin/verification/cases${status ? `?status=${encodeURIComponent(status)}` : ""}`,
      ),
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <BadgeCheck size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-foreground-muted mt-1">{t("subtitle")}</p>
        </div>
      </div>

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
        {CASE_STATUS_FILTERS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatus(s)}
            className={filterBtnCls(status === s)}
          >
            {t(`caseStatus.${s}`)}
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
                <th className={thCls}>{t("columns.submittedAt")}</th>
                <th className={thCls}>{t("columns.company")}</th>
                <th className={thCls}>{t("columns.caseType")}</th>
                <th className={thCls}>{t("columns.status")}</th>
                <th className={thCls}>{t("columns.checks")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => router.push(`/verification/${c.id}`)}
                  className="cursor-pointer bg-background-secondary hover:bg-background-tertiary transition-colors"
                >
                  <td className="px-4 py-3 text-foreground-muted whitespace-nowrap">
                    {c.submitted_at ? (
                      <time dateTime={c.submitted_at} title={c.submitted_at}>
                        {formatTashkent(c.submitted_at)}
                      </time>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/verification/${c.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="font-medium text-foreground hover:text-accent"
                    >
                      {c.company_name || t("unnamedCompany")}
                    </Link>
                    <p className="text-xs text-foreground-muted mt-0.5">
                      {t("inn")}: {c.company_tax_id || "—"}
                    </p>
                  </td>
                  <td className="px-4 py-3 text-foreground-muted whitespace-nowrap">
                    <CaseTypeLabel caseType={c.case_type} />
                  </td>
                  <td className="px-4 py-3">
                    <CaseStatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {Object.keys(c.checks).length === 0 ? (
                        <span className="text-xs text-foreground-muted">—</span>
                      ) : (
                        Object.entries(c.checks).map(([checkType, checkStatus]) => (
                          <CheckChip
                            key={checkType}
                            checkType={checkType}
                            status={checkStatus}
                          />
                        ))
                      )}
                    </div>
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
