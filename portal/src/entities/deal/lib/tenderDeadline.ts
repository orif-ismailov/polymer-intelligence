/**
 * How long a supplier still has to quote on a tender.
 *
 * A tender takes quotes for `validity_days` from `created_at`. The API sends both
 * and never the end date, so the list derives it here — the one fact a supplier
 * scans the list for, and the old card never showed.
 *
 * Deliberately imports nothing, so `tenderDeadline.test.ts` runs under plain
 * `node --test` in a package whose only runner is Playwright.
 */

const DAY_MS = 24 * 60 * 60 * 1000;

/** Three days is when a quote needs preparing now rather than this week. */
const WARNING_DAYS = 3;

export type DeadlineTone = "neutral" | "warning" | "lastDay" | "closed" | "unknown";

export interface TenderDeadline {
  /** Whole days left, rounded UP: two days and an hour is three days to act. */
  daysLeft: number;
  tone: DeadlineTone;
}

export function tenderDeadline(
  createdAt: string,
  validityDays: number,
  now: Date = new Date(),
): TenderDeadline {
  const created = new Date(createdAt).getTime();
  if (Number.isNaN(created)) return { daysLeft: 0, tone: "unknown" };

  const remaining = created + validityDays * DAY_MS - now.getTime();
  if (remaining <= 0) return { daysLeft: 0, tone: "closed" };

  const daysLeft = Math.ceil(remaining / DAY_MS);
  if (remaining < DAY_MS) return { daysLeft, tone: "lastDay" };
  if (daysLeft <= WARNING_DAYS) return { daysLeft, tone: "warning" };
  return { daysLeft, tone: "neutral" };
}
