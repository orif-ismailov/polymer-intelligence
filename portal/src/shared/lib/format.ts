/**
 * Display formatters. Times are stored UTC and shown in Asia/Tashkent.
 */

const TZ_DISPLAY = "Asia/Tashkent";

/** Locale tag Intl understands, derived from the app's i18n language. */
function intlLocale(lang: string): string {
  switch (lang) {
    case "uz":
      return "uz-UZ";
    case "en":
      return "en-US";
    default:
      return "ru-RU";
  }
}

/** Format an ISO datetime string as a localized date + time in Tashkent. */
export function formatDateTime(iso: string | null | undefined, lang = "ru"): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(intlLocale(lang), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: TZ_DISPLAY,
  }).format(date);
}

/** Format an ISO datetime string as a localized date only. */
export function formatDate(iso: string | null | undefined, lang = "ru"): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(intlLocale(lang), {
    dateStyle: "medium",
    timeZone: TZ_DISPLAY,
  }).format(date);
}

/** Human-readable byte size. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

/** Format a numeric-or-string money value with an ISO currency code. */
export function formatMoney(
  value: string | number | null | undefined,
  currency: string,
  lang = "ru",
): string {
  if (value == null || value === "") return "—";
  const num = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(num)) return String(value);
  try {
    return new Intl.NumberFormat(intlLocale(lang), {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(num);
  } catch {
    return `${num.toLocaleString(intlLocale(lang))} ${currency}`;
  }
}

/** Format a numeric-or-string quantity with a unit suffix. */
export function formatQty(
  value: string | number | null | undefined,
  unit: string,
  lang = "ru",
): string {
  if (value == null || value === "") return "—";
  const num = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(num)) return `${String(value)} ${unit}`;
  return `${num.toLocaleString(intlLocale(lang))} ${unit}`;
}
