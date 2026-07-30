/**
 * Phone input helpers.
 *
 * Primary market is Uzbekistan (+998 XX XXX XX XX), but international numbers
 * with a leading `+` are accepted verbatim. The mask is display-only; the value
 * sent to the backend is the E.164-ish `+<digits>` string.
 */

const UZ_PREFIX = "998";

/** Strip everything except digits. */
function digitsOnly(value: string): string {
  return value.replace(/\D+/g, "");
}

/**
 * Normalize a user-typed phone into the canonical `+<digits>` form.
 *
 * - Leading `+` → kept, digits after it preserved (international).
 * - Uzbek local forms (9 digits, or 12 digits starting with 998) → `+998…`.
 * - Empty → empty string.
 */
export function normalizePhone(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed === "") return "";

  const hasPlus = trimmed.startsWith("+");
  const digits = digitsOnly(trimmed);
  if (digits === "") return "";

  if (hasPlus) {
    return `+${digits}`;
  }
  if (digits.startsWith(UZ_PREFIX)) {
    return `+${digits}`;
  }
  // Bare local Uzbek number (e.g. 901234567) → prepend country code.
  if (digits.length === 9) {
    return `+${UZ_PREFIX}${digits}`;
  }
  return `+${digits}`;
}

/**
 * Format a raw string for display in the input. Uzbek numbers get grouped
 * spacing; other international numbers are shown as `+<digits>` untouched.
 */
export function formatPhoneMask(raw: string): string {
  const normalized = normalizePhone(raw);
  if (normalized === "") return "";

  const body = normalized.slice(1); // drop leading '+'
  if (body.startsWith(UZ_PREFIX)) {
    const rest = body.slice(UZ_PREFIX.length).slice(0, 9);
    const parts: string[] = [`+${UZ_PREFIX}`];
    if (rest.length > 0) parts.push(rest.slice(0, 2));
    if (rest.length > 2) parts.push(rest.slice(2, 5));
    if (rest.length > 5) parts.push(rest.slice(5, 7));
    if (rest.length > 7) parts.push(rest.slice(7, 9));
    return parts.join(" ").trimEnd();
  }
  return `+${body}`;
}

/** A phone is submittable once it has a country code + at least 9 subscriber digits. */
export function isValidPhone(raw: string): boolean {
  const normalized = normalizePhone(raw);
  const digits = normalized.replace(/\D+/g, "");
  return digits.length >= 11 && digits.length <= 15;
}
