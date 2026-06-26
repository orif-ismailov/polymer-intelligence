"use client";

/**
 * StatusChip — request status badge.
 * Uses token classes only (no hardcoded hex). UI-SPEC §Color / Status tokens.
 * Color alone never conveys status: label text + color (accessibility).
 */

import { useTranslations } from "next-intl";

const STATUS_CLASSES: Record<string, string> = {
  new: "text-status-new border-status-new",
  viewed: "text-status-viewed border-status-viewed",
  in_progress: "text-status-in-progress border-status-in-progress",
  offer_sent: "text-status-offer-sent border-status-offer-sent",
  matched: "text-status-matched border-status-matched",
  closed: "text-status-closed border-status-closed",
  cancelled: "text-status-cancelled border-status-cancelled",
};

const STATUS_KEYS: Record<string, string> = {
  new: "status.new",
  viewed: "status.viewed",
  in_progress: "status.in_progress",
  offer_sent: "status.offer_sent",
  matched: "status.matched",
  closed: "status.closed",
  cancelled: "status.cancelled",
};

interface StatusChipProps {
  status: string;
  className?: string;
}

export function StatusChip({ status, className = "" }: StatusChipProps) {
  const t = useTranslations("common");
  const colorClasses = STATUS_CLASSES[status] ?? "text-foreground-muted border-foreground-muted";
  const labelKey = STATUS_KEYS[status];
  const label = labelKey ? t(labelKey) : status;

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${colorClasses} ${className}`}
    >
      {label}
    </span>
  );
}
