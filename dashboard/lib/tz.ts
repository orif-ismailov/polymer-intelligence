/**
 * Asia/Tashkent timezone display utilities.
 * DEC-tz-handling: UTC in DB, Asia/Tashkent on display.
 * Use Intl.DateTimeFormat (Don't Hand-Roll — RESEARCH.md).
 */

const TZ = "Asia/Tashkent";

const dateTimeFormatter = new Intl.DateTimeFormat("ru-RU", {
  timeZone: TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const dateFormatter = new Intl.DateTimeFormat("ru-RU", {
  timeZone: TZ,
  year: "numeric",
  month: "short",
  day: "numeric",
});

/**
 * Format an ISO 8601 string for display in Asia/Tashkent timezone.
 * Example output: "17.06.2026, 16:45"
 */
export function formatTashkent(iso: string): string {
  const date = new Date(iso);
  if (isNaN(date.getTime())) return "—";
  return dateTimeFormatter.format(date);
}

/**
 * Format an ISO 8601 string as a date-only string in Asia/Tashkent.
 * Example output: "17 июн. 2026 г."
 */
export function formatTashkentDate(iso: string): string {
  const date = new Date(iso);
  if (isNaN(date.getTime())) return "—";
  return dateFormatter.format(date);
}

/**
 * Return a human-readable relative time string ("2 min ago", "3 hours ago", "yesterday").
 * Used for "Updated N min ago" / Posted Time displays.
 */
export function relativeTime(iso: string): string {
  const date = new Date(iso);
  if (isNaN(date.getTime())) return "—";

  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return "just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  if (diffHour < 24) return `${diffHour}h ago`;
  if (diffDay === 1) return "yesterday";
  if (diffDay < 7) return `${diffDay} days ago`;

  // Fall back to formatted date for older entries
  return formatTashkentDate(iso);
}
