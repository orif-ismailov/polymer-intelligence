"use client";

/**
 * Verification / company status chips — R1 W6.
 *
 * Small colored badges for case status, per-check status, and company status.
 * Color alone never conveys status: every chip carries a text label too
 * (accessibility). Labels resolve through next-intl with a raw-value fallback,
 * so an unexpected backend enum value degrades gracefully instead of throwing.
 */

import { useTranslations } from "next-intl";

// ─── Color maps (raw Tailwind palette, matching reports/moderation idiom) ────

const CHECK_STATUS_CLASSES: Record<string, string> = {
  pending: "bg-background-tertiary text-foreground-muted",
  running: "bg-blue-500/20 text-blue-400",
  passed: "bg-accent/20 text-accent",
  warning: "bg-amber-500/20 text-amber-400",
  failed: "bg-red-500/20 text-red-400",
  unavailable: "bg-background-tertiary text-foreground-subtle",
  waived: "bg-violet-500/20 text-violet-400",
};

const CASE_STATUS_CLASSES: Record<string, string> = {
  draft: "bg-background-tertiary text-foreground-muted",
  submitted: "bg-blue-500/20 text-blue-400",
  checks_running: "bg-blue-500/20 text-blue-400",
  needs_info: "bg-amber-500/20 text-amber-400",
  pending_review: "bg-amber-500/20 text-amber-400",
  approved: "bg-accent/20 text-accent",
  rejected: "bg-red-500/20 text-red-400",
  cancelled: "bg-background-tertiary text-foreground-subtle",
};

const FALLBACK_CLASS = "bg-background-tertiary text-foreground-muted";

const baseChip =
  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap";

// ─── Label helpers ────────────────────────────────────────────────────────────

/**
 * Resolve a translation, falling back to the raw value when the key is missing.
 * next-intl throws in dev on a missing key; wrapping it keeps unexpected backend
 * enum values from crashing the page.
 */
function useSafeLabel(namespace: "verification") {
  const t = useTranslations(namespace);
  return (key: string, fallback: string): string => {
    try {
      return t(key);
    } catch {
      return fallback;
    }
  };
}

// ─── Components ────────────────────────────────────────────────────────────────

export function CheckChip({ checkType, status }: { checkType: string; status: string }) {
  const label = useSafeLabel("verification");
  const cls = CHECK_STATUS_CLASSES[status] ?? FALLBACK_CLASS;
  const typeLabel = label(`checkType.${checkType}`, checkType);
  const statusLabel = label(`checkStatus.${status}`, status);
  return (
    <span className={`${baseChip} ${cls}`} title={`${typeLabel}: ${statusLabel}`}>
      {typeLabel}: {statusLabel}
    </span>
  );
}

export function CheckStatusBadge({ status }: { status: string }) {
  const label = useSafeLabel("verification");
  const cls = CHECK_STATUS_CLASSES[status] ?? FALLBACK_CLASS;
  return <span className={`${baseChip} ${cls}`}>{label(`checkStatus.${status}`, status)}</span>;
}

export function CaseStatusBadge({ status }: { status: string }) {
  const label = useSafeLabel("verification");
  const cls = CASE_STATUS_CLASSES[status] ?? FALLBACK_CLASS;
  return <span className={`${baseChip} ${cls}`}>{label(`caseStatus.${status}`, status)}</span>;
}

export function CaseTypeLabel({ caseType }: { caseType: string }) {
  const label = useSafeLabel("verification");
  return <>{label(`caseType.${caseType}`, caseType)}</>;
}
