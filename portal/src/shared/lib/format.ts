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

/**
 * All-numeric date (`12.03.2020`).
 *
 * The mockups write calendar dates this way wherever they line up in a column —
 * a registration date next to an id, a certificate date in a summary — because
 * "12 мар. 2020 г." is a different width in every month and the column stops
 * scanning. Prose keeps {@link formatDate}.
 */
export function formatDateShort(iso: string | null | undefined, lang = "ru"): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(intlLocale(lang), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: TZ_DISPLAY,
  }).format(date);
}

/**
 * Localized country name for an ISO-3166 alpha-2 code.
 *
 * `Intl.DisplayNames` rather than a translation table: the offer's `country`
 * column is a `char(2)`, the selectors offer a dozen or so codes, and a
 * hand-kept ru/uz/en list of country names is three files that drift. Falls back
 * to the code itself — an unknown or malformed value must still print.
 */
export function countryName(code: string | null | undefined, lang = "ru"): string {
  if (!code) return "—";
  try {
    return new Intl.DisplayNames([intlLocale(lang)], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

/**
 * Emoji flag for an ISO-3166 alpha-2 code, or `null` if there isn't one.
 *
 * The two letters map to the Unicode regional-indicator block, so this is pure
 * arithmetic — no icon set, no sprite sheet, no new dependency for the flag the
 * storefront cards show beside the country. Returns `null` rather than a
 * placeholder glyph so a caller can omit the slot entirely; a tofu box next to a
 * country name is worse than no flag.
 */
export function countryFlag(code: string | null | undefined): string | null {
  if (!code || code.length !== 2 || !/^[a-z]{2}$/i.test(code)) return null;
  const base = 0x1f1e6 - "A".charCodeAt(0);
  return String.fromCodePoint(
    ...code
      .toUpperCase()
      .split("")
      .map((c) => base + c.charCodeAt(0)),
  );
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
