import type { BadgeTone } from "@/shared/ui";

/**
 * Static enum-value → badge-tone maps. These are visual mappings, not business
 * logic — they translate a status string into a color intent for chips.
 */

export const COMPANY_STATUS_TONE: Record<string, BadgeTone> = {
  draft: "neutral",
  pending_verification: "info",
  verified: "success",
  rejected: "danger",
  suspended: "warning",
  liquidated: "neutral",
};

export const CASE_STATUS_TONE: Record<string, BadgeTone> = {
  draft: "neutral",
  submitted: "info",
  checks_running: "info",
  needs_info: "warning",
  pending_review: "info",
  approved: "success",
  rejected: "danger",
  cancelled: "neutral",
};

export const CHECK_STATUS_TONE: Record<string, BadgeTone> = {
  pending: "neutral",
  running: "info",
  passed: "success",
  warning: "warning",
  failed: "danger",
  unavailable: "neutral",
  waived: "neutral",
};

export const OFFER_STATUS_TONE: Record<string, BadgeTone> = {
  draft: "neutral",
  pending_moderation: "info",
  approved: "success",
  rejected: "danger",
  archived: "neutral",
};

export function toneFor(map: Record<string, BadgeTone>, value: string): BadgeTone {
  return map[value] ?? "neutral";
}
