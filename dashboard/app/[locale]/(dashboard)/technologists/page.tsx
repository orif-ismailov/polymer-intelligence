"use client";

/**
 * Technologist moderation (/technologists) — the expert marketplace (0055).
 *
 * A technologist is a private person. Staff issued them credentials from
 * «Кабинеты клиентов» (their application carries `applied_as=technologist`);
 * here staff decide whether the PROFILE they filled in goes into the public
 * catalog. The catalog serves the approved snapshot, so approving an edit of a
 * listed expert replaces what factories see; rejecting it leaves the old card up.
 *
 * Backed by /api/v1/admin/technologists — the `technologists` page grant, `read`
 * to see the queue and `write` to decide. The backend is the boundary; a reader
 * pressing «Одобрить» gets a 403, shown as an error.
 *
 * No hardcoded hex.
 */

import { type ReactNode, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HardHat } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiBlob, apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

// ─── Types ─────────────────────────────────────────────────────────────────────

type ProfileStatus = "draft" | "pending_review" | "published" | "rejected" | "suspended";

interface Technologist {
  id: number;
  user_account_id: number;
  account_name: string | null;
  account_phone: string | null;
  full_name: string | null;
  title: string | null;
  country: string | null;
  city: string | null;
  photo_url: string | null;
  years_experience: number | null;
  projects_count: number | null;
  countries_count: number | null;
  bio: string | null;
  industries: string[];
  processes: string[];
  materials: string[];
  equipment_brands: string[];
  work_formats: string[];
  languages: string[];
  contact_phone: string | null;
  contact_email: string | null;
  status: ProfileStatus;
  rejection_reason: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  is_listed: boolean;
  missing_fields: string[];
  rating_avg: string | null;
  rating_count: number;
  published_snapshot: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

const FILTERS = ["pending_review", "published", "rejected", "suspended", "draft", "all"] as const;

const STATUS_TONE: Record<ProfileStatus, string> = {
  pending_review: "border-urgency-medium/40 text-urgency-medium",
  published: "border-accent/30 text-accent",
  rejected: "border-urgency-high/30 text-urgency-high",
  suspended: "border-urgency-high/30 text-urgency-high",
  draft: "border-border text-foreground-muted",
};

function StatusBadge({ status }: { status: ProfileStatus }) {
  const t = useTranslations("technologists");
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${STATUS_TONE[status]}`}
    >
      {t(`status.${status}`)}
    </span>
  );
}

// ─── Detail ────────────────────────────────────────────────────────────────────

/** The LIVE portrait — behind the staff guard, so fetched with the token. */
function Portrait({ path }: { path: string }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    apiBlob(path.replace(/^\/api\/v1/, ""))
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setSrc(url);
      })
      .catch(() => setSrc(null));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [path]);
  if (!src) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element -- an object URL, not a static asset
    <img src={src} alt="" className="h-20 w-20 shrink-0 rounded-full border border-border object-cover" />
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="grid grid-cols-[9rem_minmax(0,1fr)] gap-3 py-1.5 text-sm">
      <dt className="text-foreground-muted">{label}</dt>
      <dd className="min-w-0 break-words text-foreground">{value}</dd>
    </div>
  );
}

function DetailDialog({ profile, onClose }: { profile: Technologist; onClose: () => void }) {
  const t = useTranslations("technologists");
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const decide = useMutation({
    mutationFn: (action: "approve" | "reject" | "suspend") =>
      apiFetch<Technologist>(`/admin/technologists/${profile.id}/${action}`, {
        method: "POST",
        body: action === "approve" ? undefined : JSON.stringify({ reason: reason.trim() }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-technologists"] });
      onClose();
    },
    onError: (e: unknown) =>
      setError(e instanceof ApiError && e.status === 403 ? t("forbidden") : t("saveError")),
  });

  const list = (values: string[]) => (values.length ? values.join(", ") : null);
  const labelled = (group: "process" | "industry" | "format", values: string[]) =>
    list(values.map((v) => (t.has(`${group}.${v}`) ? t(`${group}.${v}`) : v)));
  const needsReason = reason.trim().length === 0;

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            {profile.full_name ?? profile.account_name ?? `#${profile.id}`}
            <StatusBadge status={profile.status} />
          </DialogTitle>
          <DialogDescription>{profile.title ?? "—"}</DialogDescription>
        </DialogHeader>

        {profile.is_listed && profile.status !== "published" && (
          <p className="rounded-lg border border-urgency-medium/30 bg-urgency-medium/10 p-3 text-sm text-urgency-medium">
            {t("editOfListed")}
          </p>
        )}

        <div className="flex gap-4">
          {profile.photo_url && <Portrait path={profile.photo_url} />}
          <dl className="min-w-0 flex-1">
            <Row label={t("fields.account")} value={`${profile.account_name ?? "—"} · ${profile.account_phone ?? "—"}`} />
            <Row label={t("fields.location")} value={[profile.city, profile.country].filter(Boolean).join(", ")} />
            <Row label={t("fields.years")} value={profile.years_experience} />
            <Row label={t("fields.projects")} value={profile.projects_count} />
            <Row label={t("fields.countries")} value={profile.countries_count} />
            <Row label={t("fields.processes")} value={labelled("process", profile.processes)} />
            <Row label={t("fields.materials")} value={list(profile.materials)} />
            <Row label={t("fields.industries")} value={labelled("industry", profile.industries)} />
            <Row label={t("fields.equipment")} value={list(profile.equipment_brands)} />
            <Row label={t("fields.formats")} value={labelled("format", profile.work_formats)} />
            <Row label={t("fields.languages")} value={list(profile.languages)} />
            <Row label={t("fields.contacts")} value={[profile.contact_phone, profile.contact_email].filter(Boolean).join(" · ")} />
            <Row label={t("fields.submittedAt")} value={profile.submitted_at ? formatTashkent(profile.submitted_at) : null} />
            <Row label={t("fields.reason")} value={profile.rejection_reason} />
          </dl>
        </div>
        {profile.bio && <p className="whitespace-pre-line text-sm text-foreground-muted">{profile.bio}</p>}

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-foreground">{t("reasonLabel")}</span>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
          <span className="text-xs text-foreground-muted">{t("reasonHint")}</span>
        </label>

        {error && (
          <div className="rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-3 text-sm text-urgency-high">
            {error}
          </div>
        )}

        <DialogFooter className="flex-wrap gap-2">
          {profile.status === "pending_review" && (
            <>
              <Button variant="ghost" disabled={decide.isPending || needsReason} onClick={() => decide.mutate("reject")}>
                {t("reject")}
              </Button>
              <Button disabled={decide.isPending} onClick={() => decide.mutate("approve")}>
                {t("approve")}
              </Button>
            </>
          )}
          {profile.status !== "suspended" && profile.is_listed && (
            <Button variant="ghost" disabled={decide.isPending || needsReason} onClick={() => decide.mutate("suspend")}>
              {t("suspend")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function TechnologistsPage() {
  const t = useTranslations("technologists");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("pending_review");
  const [open, setOpen] = useState<Technologist | null>(null);

  const { data = [], isLoading, error } = useQuery<Technologist[]>({
    queryKey: ["admin-technologists", filter],
    queryFn: () =>
      apiFetch<Technologist[]>(`/admin/technologists${filter === "all" ? "" : `?status=${filter}`}`),
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <HardHat size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("pageTitle")}</h1>
          <p className="mt-0.5 text-sm text-foreground-muted">{t("pageSubtitle")}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <Button key={f} variant={filter === f ? "default" : "ghost"} size="sm" onClick={() => setFilter(f)}>
            {f === "all" ? t("filterAll") : t(`status.${f}`)}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-background-tertiary" />
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-4 text-sm text-urgency-high">
          {error instanceof ApiError && error.status === 403 ? t("forbidden") : t("loadError")}
        </div>
      ) : data.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <HardHat size={32} className="text-foreground-muted" aria-hidden="true" />
          <p className="text-sm text-foreground-muted">{t("empty")}</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-tertiary">
              <tr>
                {["expert", "processes", "status", "submittedAt"].map((c) => (
                  <th key={c} className="px-4 py-3 text-start text-xs font-semibold uppercase tracking-wider text-foreground-muted">
                    {t(`table.${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.map((p) => (
                <tr
                  key={p.id}
                  className="cursor-pointer bg-background-secondary transition-colors hover:bg-background-tertiary"
                  onClick={() => setOpen(p)}
                >
                  <td className="px-4 py-3">
                    <span className="font-medium text-foreground">{p.full_name ?? p.account_name ?? `#${p.id}`}</span>
                    <span className="block text-xs text-foreground-muted">{p.title ?? "—"}</span>
                  </td>
                  <td className="px-4 py-3 text-foreground-muted">
                    {p.processes.map((v) => (t.has(`process.${v}`) ? t(`process.${v}`) : v)).join(", ") || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={p.status} />
                  </td>
                  <td className="px-4 py-3 text-foreground-muted">
                    {p.submitted_at ? formatTashkent(p.submitted_at) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {open && <DetailDialog profile={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
