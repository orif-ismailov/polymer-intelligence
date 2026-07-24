"use client";

/**
 * Company detail (/companies/[id]) — R1 W6.
 *
 * Full company profile + roles. Admins can suspend a verified company or
 * reinstate a suspended one. Backed by GET /admin/companies/{id} and the
 * POST suspend/reinstate endpoints (mutations are admin-only — the UI mirrors
 * the backend require_admin gate).
 */

import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Building2, PauseCircle, PlayCircle } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";
import { useAuth } from "@/hooks/useAuth";
import { CompanyStatusBadge, CompanyRoleBadge } from "@/components/verification/company-status";

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

// ─── Page ────────────────────────────────────────────────────────────────────

export default function CompanyDetailPage() {
  const t = useTranslations("companies");
  const params = useParams<{ id: string }>();
  const companyId = params.id;
  const qc = useQueryClient();
  const { role } = useAuth();
  const isAdmin = role === "admin";

  const queryKey = ["company", companyId];

  const { data, isLoading, isError } = useQuery<CompanyProfile>({
    queryKey,
    queryFn: () => apiFetch<CompanyProfile>(`/admin/companies/${companyId}`),
  });

  const act = useMutation({
    mutationFn: (action: "suspend" | "reinstate") =>
      apiFetch(`/admin/companies/${companyId}/${action}`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <div className="h-8 w-48 rounded bg-background-tertiary animate-pulse" />
        <div className="h-48 rounded-lg bg-background-tertiary animate-pulse" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <BackLink label={t("back")} />
        <p className="text-sm text-red-400">{t("error")}</p>
      </div>
    );
  }

  const company = data;

  return (
    <div className="flex flex-col gap-6 p-6">
      <BackLink label={t("back")} />

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Building2 size={24} className="text-foreground-muted" aria-hidden="true" />
          <div>
            <h1 className="text-xl font-semibold text-foreground">
              {company.legal_name || company.short_name || t("unnamed")}
            </h1>
            <p className="text-sm text-foreground-muted mt-1">
              {t("columns.inn")}: {company.tax_id || "—"} · {company.public_id}
            </p>
          </div>
        </div>
        <CompanyStatusBadge status={company.status} />
      </div>

      {/* Admin actions */}
      {isAdmin && (company.status === "verified" || company.status === "suspended") && (
        <div className="flex flex-wrap gap-2">
          {company.status === "verified" && (
            <button
              type="button"
              disabled={act.isPending}
              onClick={() => act.mutate("suspend")}
              className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium text-orange-400 hover:bg-background-tertiary disabled:opacity-50"
            >
              <PauseCircle size={16} aria-hidden="true" /> {t("suspend")}
            </button>
          )}
          {company.status === "suspended" && (
            <button
              type="button"
              disabled={act.isPending}
              onClick={() => act.mutate("reinstate")}
              className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
            >
              <PlayCircle size={16} aria-hidden="true" /> {t("reinstate")}
            </button>
          )}
        </div>
      )}

      {/* Profile */}
      <section className="rounded-lg border border-border bg-background-secondary p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground-muted">
          {t("profile.title")}
        </h2>
        <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label={t("profile.legalName")} value={company.legal_name} />
          <Field label={t("profile.shortName")} value={company.short_name} />
          <Field label={t("profile.publicId")} value={company.public_id} />
          <Field label={t("profile.jurisdiction")} value={company.jurisdiction} />
          <Field label={t("profile.taxId")} value={company.tax_id} />
          <Field label={t("profile.legalForm")} value={company.legal_form} />
          <Field label={t("profile.director")} value={company.director_name} />
          <Field label={t("profile.address")} value={company.legal_address} />
          <Field
            label={t("profile.verifiedAt")}
            value={company.verified_at ? formatTashkent(company.verified_at) : null}
          />
          <Field
            label={t("profile.reverificationDue")}
            value={
              company.reverification_due_at
                ? formatTashkent(company.reverification_due_at)
                : null
            }
          />
        </dl>
      </section>

      {/* Roles */}
      <section className="rounded-lg border border-border bg-background-secondary p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground-muted">
          {t("profile.roles")}
        </h2>
        {company.roles.length === 0 ? (
          <p className="mt-3 text-sm text-foreground-muted">{t("noRoles")}</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {company.roles.map((r) => (
              <li key={r.role} className="flex items-center gap-3">
                <CompanyRoleBadge role={r.role} status={r.status} />
                <span className="text-xs text-foreground-muted">{r.status}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-xs text-foreground-muted">{label}</dt>
      <dd className="mt-1 text-sm text-foreground break-words">{value || "—"}</dd>
    </div>
  );
}

function BackLink({ label }: { label: string }) {
  return (
    <Link
      href="/companies"
      className="inline-flex items-center gap-1.5 text-sm text-foreground-muted hover:text-foreground"
    >
      <ArrowLeft size={16} aria-hidden="true" /> {label}
    </Link>
  );
}
