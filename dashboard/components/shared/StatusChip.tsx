"use client";

/**
 * StatusChip — request status badge.
 * Uses token classes only (no hardcoded hex). UI-SPEC §Color / Status tokens.
 * Color alone never conveys status: label text + color (accessibility).
 */

const STATUS_CLASSES: Record<string, string> = {
  new: "text-status-new border-status-new",
  viewed: "text-status-viewed border-status-viewed",
  in_progress: "text-status-in-progress border-status-in-progress",
  offer_sent: "text-status-offer-sent border-status-offer-sent",
  matched: "text-status-matched border-status-matched",
  closed: "text-status-closed border-status-closed",
  cancelled: "text-status-cancelled border-status-cancelled",
};

const STATUS_LABELS: Record<string, string> = {
  new: "New",
  viewed: "Viewed",
  in_progress: "In Progress",
  offer_sent: "Offer Sent",
  matched: "Matched",
  closed: "Closed",
  cancelled: "Cancelled",
};

interface StatusChipProps {
  status: string;
  className?: string;
}

export function StatusChip({ status, className = "" }: StatusChipProps) {
  const colorClasses = STATUS_CLASSES[status] ?? "text-foreground-muted border-foreground-muted";
  const label = STATUS_LABELS[status] ?? status;

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${colorClasses} ${className}`}
    >
      {label}
    </span>
  );
}
