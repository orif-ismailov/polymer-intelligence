"use client";

/**
 * Company status badge — R1 W6.
 *
 * Separate from the verification chips because the company label set lives under
 * the `companies` i18n namespace. Same graceful-fallback contract: next-intl
 * returns the key string (it does not throw) on a missing message, so we probe
 * with `t.has()` and fall back to the raw enum value.
 */

import { useTranslations } from "next-intl";

const COMPANY_STATUS_CLASSES: Record<string, string> = {
  draft: "bg-background-tertiary text-foreground-muted",
  pending_verification: "bg-amber-500/20 text-amber-400",
  verified: "bg-accent/20 text-accent",
  rejected: "bg-red-500/20 text-red-400",
  suspended: "bg-orange-500/20 text-orange-400",
  liquidated: "bg-background-tertiary text-foreground-subtle",
};

const FALLBACK_CLASS = "bg-background-tertiary text-foreground-muted";

const baseChip =
  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap";

export function CompanyStatusBadge({ status }: { status: string }) {
  const t = useTranslations("companies");
  const cls = COMPANY_STATUS_CLASSES[status] ?? FALLBACK_CLASS;
  const key = `status.${status}`;
  const label = t.has(key) ? t(key) : status;
  return <span className={`${baseChip} ${cls}`}>{label}</span>;
}

export function CompanyRoleBadge({ role, status }: { role: string; status: string }) {
  const t = useTranslations("companies");
  const key = `role.${role}`;
  const roleLabel = t.has(key) ? t(key) : role;
  const active = status === "active" || status === "verified" || status === "approved";
  const cls = active
    ? "bg-accent/20 text-accent"
    : "bg-background-tertiary text-foreground-muted";
  return (
    <span className={`${baseChip} ${cls}`} title={`${roleLabel}: ${status}`}>
      {roleLabel}
    </span>
  );
}
