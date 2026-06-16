/**
 * Date/time formatting utilities for the Polymer Intelligence Web App.
 *
 * DEC-tz-handling: DB stores UTC; display in Asia/Tashkent per dev-spec §3.
 * The backend's backend/app/core/time.py uses Asia/Tashkent for all date
 * operations; the frontend mirrors this via Intl.DateTimeFormat.
 */

import i18n from "../i18n";

/**
 * Format a UTC ISO datetime string for display in Asia/Tashkent local time.
 *
 * Uses the current i18n language (ru/uz) for locale-aware formatting.
 * dateStyle: 'short' + timeStyle: 'short' → e.g. "16.06.2026, 14:30" (ru)
 *
 * @param utcIso - UTC ISO datetime string (e.g. "2026-06-16T09:30:00Z")
 * @returns Formatted string in Asia/Tashkent timezone
 */
export function formatTashkent(utcIso: string): string {
  const lang = i18n.language ?? "ru";
  try {
    return new Intl.DateTimeFormat(lang, {
      timeZone: "Asia/Tashkent",
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(utcIso));
  } catch {
    // Fallback: return the raw string if Intl fails
    return utcIso;
  }
}
