"use client";

/**
 * Verification case detail (/verification/[id]) — R1 W6.
 *
 * Full case review: declared company profile, per-check results, uploaded
 * documents (presigned download links), audit trail, and the analyst decision
 * (approve / reject / request-info) with an optional note. Admins can also waive
 * an individual check with a reason. Backed by GET /admin/verification/cases/{id}
 * and the POST decision/waive endpoints (require_analyst_or_admin; waive is
 * admin-only on the backend too — the UI mirrors that gate).
 */

import { useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BadgeCheck,
  Check,
  FileText,
  History,
  Landmark,
  ShieldOff,
  X,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { ApiError, apiFetch, apiUpload } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";
import { useAuth } from "@/hooks/useAuth";
import {
  CaseStatusBadge,
  CaseTypeLabel,
  CheckStatusBadge,
} from "@/components/verification/chips";
import { CompanyStatusBadge, CompanyRoleBadge } from "@/components/verification/company-status";
import { CompanyProfileSections } from "@/components/verification/company-profile-sections";

// ─── Types (match backend response shapes exactly) ────────────────────────────

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
  declared_roles: string[];
  confirmed_roles: string[];
  manufacturer_profile: Record<string, unknown> | null;
  logistics_profile: Record<string, unknown> | null;
  laboratory_profile: Record<string, unknown> | null;
}

interface BankAccount {
  id: number;
  bank_mfo: string;
  account_masked: string;
  currency: string;
  status: string;
}

interface VerificationCheck {
  id: number;
  check_type: string;
  status: string;
  result: Record<string, unknown> | null;
  attempts: number;
  last_error: string | null;
  waived_by: number | null;
  waive_reason: string | null;
}

interface VerificationDocument {
  id: number;
  kind: string;
  mime_type: string | null;
  size_bytes: number | null;
  status: string;
  sha256: string;
  download_url: string;
}

interface AuditEntry {
  id: number;
  action: string;
  staff_user_id: number | null;
  details: Record<string, unknown>;
  created_at: string;
}

/**
 * One immutable state-registry observation (R6 / P7.c).
 *
 * `source` is the whole point: `manual` means a member of staff read an open
 * service and transcribed it, `registry` means an API answered. The verdict is
 * computed from the payload by the same backend function either way, so this
 * field is the only record of which it was.
 */
interface RegistrySnapshot {
  id: number;
  kind: string;
  source: string;
  provider: string;
  payload: Record<string, unknown>;
  raw_status: string | null;
  note: string | null;
  created_by: number | null;
  evidence_url: string | null;
  fetched_at: string;
  created_at: string;
}

interface VerificationCaseDetail {
  id: number;
  case_type: string;
  status: string;
  submitted_at: string | null;
  decided_at: string | null;
  decided_by: number | null;
  decision_note: string | null;
  company: CompanyProfile;
  bank_accounts: BankAccount[];
  checks: VerificationCheck[];
  documents: VerificationDocument[];
  audit: AuditEntry[];
  /** Newest snapshot per kind. An absent kind was never checked — which must not
   *  look like "checked, found nothing". */
  registry: Record<string, RegistrySnapshot>;
}

/** The three lookups, in the order an operator works them. */
const REGISTRY_KINDS = ["company", "vat", "licenses"] as const;

const REGISTRY_STATUSES = ["active", "liquidated", "suspended", "unknown"] as const;

type DecisionAction = "approve" | "reject" | "request-info";

const DECIDED_STATUSES = new Set(["approved", "rejected", "cancelled"]);

// ─── Page ────────────────────────────────────────────────────────────────────

export default function VerificationCaseDetailPage() {
  const t = useTranslations("verification");
  const params = useParams<{ id: string }>();
  const caseId = params.id;
  const qc = useQueryClient();
  const { role } = useAuth();
  const isAdmin = role === "admin";

  const [note, setNote] = useState("");
  const [conflict, setConflict] = useState(false);

  const queryKey = ["verification-case", caseId];

  const { data, isLoading, isError } = useQuery<VerificationCaseDetail>({
    queryKey,
    queryFn: () => apiFetch<VerificationCaseDetail>(`/admin/verification/cases/${caseId}`),
  });

  const decide = useMutation({
    mutationFn: (action: DecisionAction) =>
      apiFetch(`/admin/verification/cases/${caseId}/${action}`, {
        method: "POST",
        body: JSON.stringify({ note: note.trim() || null }),
      }),
    onMutate: () => setConflict(false),
    onSuccess: () => {
      setNote("");
      void qc.invalidateQueries({ queryKey });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        // Already decided by someone else — surface a message and refetch.
        setConflict(true);
        void qc.invalidateQueries({ queryKey });
      }
    },
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <div className="h-8 w-48 rounded bg-background-tertiary animate-pulse" />
        <div className="h-40 rounded-lg bg-background-tertiary animate-pulse" />
        <div className="h-40 rounded-lg bg-background-tertiary animate-pulse" />
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

  const c = data;
  const alreadyDecided = DECIDED_STATUSES.has(c.status);

  return (
    <div className="flex flex-col gap-6 p-6">
      <BackLink label={t("back")} />

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <BadgeCheck size={24} className="text-foreground-muted" aria-hidden="true" />
          <div>
            <h1 className="text-xl font-semibold text-foreground">
              {c.company.legal_name || c.company.short_name || t("unnamedCompany")}
            </h1>
            <p className="text-sm text-foreground-muted mt-1">
              <CaseTypeLabel caseType={c.case_type} /> · {t("inn")}: {c.company.tax_id || "—"}
            </p>
          </div>
        </div>
        <CaseStatusBadge status={c.status} />
      </div>

      {conflict && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-400">
          {t("decision.conflict")}
        </div>
      )}

      {/* Company profile */}
      <section className="rounded-lg border border-border bg-background-secondary p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground-muted">
          {t("profile.title")}
        </h2>
        <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label={t("profile.legalName")} value={c.company.legal_name} />
          <Field label={t("profile.shortName")} value={c.company.short_name} />
          <Field label={t("profile.publicId")} value={c.company.public_id} />
          <Field label={t("profile.jurisdiction")} value={c.company.jurisdiction} />
          <Field label={t("profile.legalForm")} value={c.company.legal_form} />
          <Field label={t("profile.director")} value={c.company.director_name} />
          <Field label={t("profile.address")} value={c.company.legal_address} />
          <div>
            <dt className="text-xs text-foreground-muted">{t("profile.status")}</dt>
            <dd className="mt-1">
              <CompanyStatusBadge status={c.company.status} />
            </dd>
          </div>
          <Field
            label={t("profile.verifiedAt")}
            value={c.company.verified_at ? formatTashkent(c.company.verified_at) : null}
          />
        </dl>

        {c.company.roles.length > 0 && (
          <div className="mt-4 flex flex-col gap-3">
            <p className="text-xs text-foreground-muted">{t("profile.roles")}</p>
            <RoleGroup
              title={t("profile.rolesConfirmed")}
              roles={c.company.roles.filter((r) => r.status === "confirmed")}
            />
            <RoleGroup
              title={t("profile.rolesDeclared")}
              roles={c.company.roles.filter((r) => r.status === "declared")}
            />
            <RoleGroup
              title={t("profile.rolesRevoked")}
              roles={c.company.roles.filter((r) => r.status === "revoked")}
            />
          </div>
        )}

        {c.bank_accounts.length > 0 && (
          <div className="mt-4">
            <p className="text-xs text-foreground-muted">{t("profile.bankAccounts")}</p>
            <ul className="mt-1 flex flex-col gap-1">
              {c.bank_accounts.map((b) => (
                <li key={b.id} className="text-sm text-foreground">
                  {b.account_masked} · {t("profile.mfo")} {b.bank_mfo} · {b.currency}
                  <span className="ms-2 text-xs text-foreground-muted">({b.status})</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* Account-type profile data — manufacturer capacity, carrier coverage,
          lab accreditation. Only the section matching the company's account
          type renders. */}
      <CompanyProfileSections
        manufacturerProfile={c.company.manufacturer_profile}
        logisticsProfile={c.company.logistics_profile}
        laboratoryProfile={c.company.laboratory_profile}
      />

      {/* Checks */}
      <section className="rounded-lg border border-border bg-background-secondary p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground-muted">
          {t("checks.title")}
        </h2>
        {c.checks.length === 0 ? (
          <p className="mt-3 text-sm text-foreground-muted">{t("checks.empty")}</p>
        ) : (
          <div className="mt-3 flex flex-col gap-3">
            {c.checks.map((check) => (
              <CheckRow key={check.id} check={check} isAdmin={isAdmin} queryKey={queryKey} />
            ))}
          </div>
        )}
      </section>

      {/* State registries (R6 / P7.c) */}
      <RegistrySection
        caseId={caseId}
        snapshots={c.registry}
        queryKey={queryKey}
        alreadyDecided={alreadyDecided}
      />

      {/* Documents */}
      <section className="rounded-lg border border-border bg-background-secondary p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground-muted">
          {t("documents.title")}
        </h2>
        {c.documents.length === 0 ? (
          <p className="mt-3 text-sm text-foreground-muted">{t("documents.empty")}</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {c.documents.map((doc) => (
              <li
                key={doc.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-background p-3"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText size={16} className="text-foreground-muted flex-shrink-0" aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      <DocKindLabel kind={doc.kind} />
                    </p>
                    <p className="text-xs text-foreground-muted">
                      {doc.mime_type || "—"}
                      {doc.size_bytes != null ? ` · ${formatBytes(doc.size_bytes)}` : ""}
                      {` · ${doc.status}`}
                    </p>
                  </div>
                </div>
                <a
                  href={doc.download_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-background-tertiary"
                >
                  {t("documents.download")}
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Audit trail */}
      <section className="rounded-lg border border-border bg-background-secondary p-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-foreground-muted">
          <History size={16} aria-hidden="true" /> {t("audit.title")}
        </h2>
        {c.audit.length === 0 ? (
          <p className="mt-3 text-sm text-foreground-muted">{t("audit.empty")}</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {c.audit.map((entry) => (
              <li key={entry.id} className="border-s-2 border-border ps-3">
                <p className="text-sm text-foreground">
                  {entry.action}
                  {entry.staff_user_id != null && (
                    <span className="ms-2 text-xs text-foreground-muted">
                      {t("audit.staff")} #{entry.staff_user_id}
                    </span>
                  )}
                </p>
                <p className="text-xs text-foreground-muted">
                  <time dateTime={entry.created_at} title={entry.created_at}>
                    {formatTashkent(entry.created_at)}
                  </time>
                </p>
                {Object.keys(entry.details).length > 0 && (
                  <JsonBlock value={entry.details} />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Decision */}
      <section className="rounded-lg border border-border bg-background-secondary p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground-muted">
          {t("decision.title")}
        </h2>

        {alreadyDecided ? (
          <div className="mt-3 text-sm text-foreground-muted">
            {t("decision.decidedAt")}:{" "}
            {c.decided_at ? formatTashkent(c.decided_at) : "—"}
            {c.decision_note && (
              <p className="mt-2 italic text-foreground">“{c.decision_note}”</p>
            )}
          </div>
        ) : (
          <>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t("decision.notePlaceholder")}
              rows={3}
              className="mt-3 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate("approve")}
                className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
              >
                <Check size={16} aria-hidden="true" /> {t("decision.approve")}
              </button>
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate("reject")}
                className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium text-red-400 hover:bg-background-tertiary disabled:opacity-50"
              >
                <X size={16} aria-hidden="true" /> {t("decision.reject")}
              </button>
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate("request-info")}
                className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary disabled:opacity-50"
              >
                {t("decision.requestInfo")}
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

// ─── State registries (R6 / P7.c) ─────────────────────────────────────────────

/**
 * The pre-ПЦД bridge, made visible.
 *
 * There is no realtime registry API for private companies yet, so the channel
 * that works today is a person: staff open my.soliq.uz / license.gov.uz /
 * registr.stat.uz, read the answer, and record it here with a screenshot. The
 * backend derives the verification verdict from the same pure function a future
 * ПЦД adapter will feed, so nothing about this form makes the result "weaker" —
 * only the snapshot's `source` says a human transcribed it.
 *
 * Each row shows the LATEST snapshot; re-checking appends rather than replaces,
 * because the history of who said what and when is the evidence.
 */
function RegistrySection({
  caseId,
  snapshots,
  queryKey,
  alreadyDecided,
}: {
  caseId: string;
  snapshots: Record<string, RegistrySnapshot>;
  queryKey: (string | undefined)[];
  alreadyDecided: boolean;
}) {
  const t = useTranslations("verification");
  const qc = useQueryClient();

  const [kind, setKind] = useState<string>("company");
  const [registryStatus, setRegistryStatus] = useState<string>("active");
  const [rawStatus, setRawStatus] = useState("");
  const [name, setName] = useState("");
  const [director, setDirector] = useState("");
  const [registered, setRegistered] = useState(true);
  const [certificateNo, setCertificateNo] = useState("");
  const [note, setNote] = useState("");
  const [evidence, setEvidence] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  // A file input keeps the browser-owned filename it displays even after the
  // React state behind it is cleared, so after a successful submit the field
  // would still show a screenshot that is NOT going to be sent. Bumping this key
  // remounts the input, which is the only way to clear what the user sees.
  const [fileKey, setFileKey] = useState(0);

  const record = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("kind", kind);
      form.append("note", note);
      form.append("raw_status", rawStatus);
      if (kind === "company") {
        form.append("status", registryStatus);
        form.append("name", name);
        form.append("director", director);
      }
      if (kind === "vat") {
        form.append("registered", registered ? "true" : "false");
        form.append("certificate_no", certificateNo);
      }
      if (evidence) form.append("evidence", evidence);
      return apiUpload<{ check_status: string | null }>(
        `/admin/verification/cases/${caseId}/registry-check`,
        form,
      );
    },
    onMutate: () => setError(null),
    onSuccess: () => {
      setRawStatus("");
      setName("");
      setDirector("");
      setCertificateNo("");
      setNote("");
      setEvidence(null);
      setFileKey((k) => k + 1);
      void qc.invalidateQueries({ queryKey });
    },
    onError: (e: unknown) => {
      const detail =
        e instanceof ApiError && e.body && typeof e.body === "object"
          ? (e.body as { detail?: unknown }).detail
          : null;
      const key = typeof detail === "string" ? `registry.errors.${detail}` : "";
      setError(key && t.has(key) ? t(key) : t("registry.errors.generic"));
    },
  });

  return (
    <section className="rounded-lg border border-border bg-background-secondary p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-foreground-muted">
        <Landmark size={16} aria-hidden="true" /> {t("registry.title")}
      </h2>
      <p className="mt-1 text-xs text-foreground-muted">{t("registry.hint")}</p>

      <div className="mt-3 flex flex-col gap-2">
        {REGISTRY_KINDS.map((k) => {
          const snapshot = snapshots[k];
          return (
            <div key={k} className="rounded-md border border-border bg-background p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium text-foreground">
                  {t(`registry.kind.${k}`)}
                </span>
                {snapshot ? (
                  <span className="text-xs text-foreground-muted">
                    {t(`registry.source.${snapshot.source}`)} ·{" "}
                    <time dateTime={snapshot.fetched_at}>
                      {formatTashkent(snapshot.fetched_at)}
                    </time>
                    {snapshot.created_by != null
                      ? ` · ${t("audit.staff")} #${snapshot.created_by}`
                      : ""}
                  </span>
                ) : (
                  <span className="text-xs text-foreground-muted">
                    {t("registry.neverChecked")}
                  </span>
                )}
              </div>
              {snapshot && (
                <>
                  <JsonBlock value={snapshot.payload} />
                  {snapshot.note && (
                    <p className="mt-1 text-xs italic text-foreground-muted">
                      “{snapshot.note}”
                    </p>
                  )}
                  {snapshot.evidence_url && (
                    <a
                      href={snapshot.evidence_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1 text-xs font-medium text-foreground hover:bg-background-tertiary"
                    >
                      {t("registry.openEvidence")}
                    </a>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>

      {alreadyDecided ? null : (
        <div className="mt-4 rounded-md border border-border bg-background p-3">
          <h3 className="text-sm font-medium text-foreground">{t("registry.form.title")}</h3>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs text-foreground-muted">
              {t("registry.form.kind")}
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                className="rounded-md border border-border bg-background-secondary px-2 py-1.5 text-sm text-foreground"
              >
                {REGISTRY_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`registry.kind.${k}`)}
                  </option>
                ))}
              </select>
            </label>

            {kind === "company" && (
              <>
                <label className="flex flex-col gap-1 text-xs text-foreground-muted">
                  {t("registry.form.status")}
                  <select
                    value={registryStatus}
                    onChange={(e) => setRegistryStatus(e.target.value)}
                    className="rounded-md border border-border bg-background-secondary px-2 py-1.5 text-sm text-foreground"
                  >
                    {REGISTRY_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {t(`registry.status.${s}`)}
                      </option>
                    ))}
                  </select>
                </label>
                <TextField
                  label={t("registry.form.name")}
                  value={name}
                  onChange={setName}
                />
                <TextField
                  label={t("registry.form.director")}
                  value={director}
                  onChange={setDirector}
                />
              </>
            )}

            {kind === "vat" && (
              <>
                <label className="flex items-center gap-2 self-end text-xs text-foreground">
                  <input
                    type="checkbox"
                    checked={registered}
                    onChange={(e) => setRegistered(e.target.checked)}
                  />
                  {t("registry.form.registered")}
                </label>
                <TextField
                  label={t("registry.form.certificateNo")}
                  value={certificateNo}
                  onChange={setCertificateNo}
                />
              </>
            )}

            <TextField
              label={t("registry.form.rawStatus")}
              value={rawStatus}
              onChange={setRawStatus}
            />
            <TextField label={t("registry.form.note")} value={note} onChange={setNote} />

            <label className="flex flex-col gap-1 text-xs text-foreground-muted sm:col-span-2">
              {t("registry.form.evidence")}
              <input
                key={fileKey}
                type="file"
                accept="image/png,image/jpeg,application/pdf"
                onChange={(e) => setEvidence(e.target.files?.[0] ?? null)}
                className="rounded-md border border-border bg-background-secondary px-2 py-1.5 text-sm text-foreground"
              />
            </label>
          </div>

          <button
            type="button"
            disabled={record.isPending}
            onClick={() => record.mutate()}
            className="mt-3 inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary disabled:opacity-50"
          >
            <Landmark size={14} aria-hidden="true" /> {t("registry.form.submit")}
          </button>
          {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        </div>
      )}
    </section>
  );
}

function TextField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-foreground-muted">
      {label}
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-background-secondary px-2 py-1.5 text-sm text-foreground"
      />
    </label>
  );
}

// ─── Check row (with admin-only waive control) ────────────────────────────────

function CheckRow({
  check,
  isAdmin,
  queryKey,
}: {
  check: VerificationCheck;
  isAdmin: boolean;
  queryKey: (string | undefined)[];
}) {
  const t = useTranslations("verification");
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [conflict, setConflict] = useState(false);

  const waive = useMutation({
    mutationFn: () =>
      apiFetch(`/admin/verification/checks/${check.id}/waive`, {
        method: "POST",
        body: JSON.stringify({ reason: reason.trim() }),
      }),
    onMutate: () => setConflict(false),
    onSuccess: () => {
      setReason("");
      void qc.invalidateQueries({ queryKey });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        setConflict(true);
        void qc.invalidateQueries({ queryKey });
      }
    },
  });

  const canWaive = isAdmin && check.status !== "waived" && check.status !== "passed";

  return (
    <div className="rounded-md border border-border bg-background p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">
            <CheckTypeLabel checkType={check.check_type} />
          </span>
          <CheckStatusBadge status={check.status} />
          {check.attempts > 0 && (
            <span className="text-xs text-foreground-muted">
              {t("checks.attempts")}: {check.attempts}
            </span>
          )}
        </div>
      </div>

      {check.last_error && (
        <p className="mt-2 text-xs text-red-400">
          {t("checks.lastError")}: {check.last_error}
        </p>
      )}

      {check.waive_reason && (
        <p className="mt-2 text-xs text-violet-400">
          {t("checks.waivedReason")}: {check.waive_reason}
        </p>
      )}

      {check.result && Object.keys(check.result).length > 0 && (
        <ResultSummary result={check.result} />
      )}

      {canWaive && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={t("checks.waiveReasonPlaceholder")}
            className="flex-1 min-w-[12rem] rounded-md border border-border bg-background-secondary px-3 py-1.5 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent"
          />
          <button
            type="button"
            disabled={waive.isPending || reason.trim() === ""}
            onClick={() => waive.mutate()}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-background-tertiary disabled:opacity-50"
          >
            <ShieldOff size={14} aria-hidden="true" /> {t("checks.waive")}
          </button>
        </div>
      )}

      {conflict && (
        <p className="mt-2 text-xs text-amber-400">{t("checks.waiveConflict")}</p>
      )}
    </div>
  );
}

// ─── Result payload rendering ─────────────────────────────────────────────────

/**
 * Render the most common structured check-result fields compactly (missing docs,
 * reasons), then fall back to a raw JSON block for anything else.
 */
function ResultSummary({ result }: { result: Record<string, unknown> }) {
  const t = useTranslations("verification");

  const missing = toStringList(result["missing_documents"]);
  const reasons = toStringList(result["reasons"]);

  const rendered = new Set(["missing_documents", "reasons"]);
  const rest: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(result)) {
    if (!rendered.has(k)) rest[k] = v;
  }

  return (
    <div className="mt-2 flex flex-col gap-2">
      {missing.length > 0 && (
        <div>
          <p className="text-xs font-medium text-foreground-muted">
            {t("checks.missingDocuments")}
          </p>
          <ul className="mt-1 list-disc ps-5 text-xs text-foreground">
            {missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      {reasons.length > 0 && (
        <div>
          <p className="text-xs font-medium text-foreground-muted">{t("checks.reasons")}</p>
          <ul className="mt-1 list-disc ps-5 text-xs text-foreground">
            {reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {Object.keys(rest).length > 0 && <JsonBlock value={rest} />}
    </div>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="mt-1 overflow-x-auto rounded-md border border-border bg-background-secondary p-2 text-xs text-foreground-muted">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

// ─── Small presentational helpers ─────────────────────────────────────────────

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-xs text-foreground-muted">{label}</dt>
      <dd className="mt-1 text-sm text-foreground break-words">{value || "—"}</dd>
    </div>
  );
}

function RoleGroup({
  title,
  roles,
}: {
  title: string;
  roles: Array<{ role: string; status: string }>;
}) {
  if (roles.length === 0) return null;
  return (
    <div>
      <p className="text-xs text-foreground-muted">{title}</p>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {roles.map((r) => (
          <CompanyRoleBadge key={r.role} role={r.role} status={r.status} />
        ))}
      </div>
    </div>
  );
}

function BackLink({ label }: { label: string }) {
  return (
    <Link
      href="/verification"
      className="inline-flex items-center gap-1.5 text-sm text-foreground-muted hover:text-foreground"
    >
      <ArrowLeft size={16} aria-hidden="true" /> {label}
    </Link>
  );
}

function CheckTypeLabel({ checkType }: { checkType: string }) {
  const t = useTranslations("verification");
  const key = `checkType.${checkType}`;
  return <>{t.has(key) ? t(key) : checkType}</>;
}

function DocKindLabel({ kind }: { kind: string }) {
  const t = useTranslations("verification");
  const key = `docKind.${kind}`;
  return <>{t.has(key) ? t(key) : kind}</>;
}

// ─── Pure utilities ────────────────────────────────────────────────────────────

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((v) => (typeof v === "string" ? v : JSON.stringify(v)));
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
