export * from "./enums";

/** Relative base — the SPA calls the API same-origin (dev proxy / prod nginx). */
export const API_BASE = "/api/v1";

/** localStorage key for the last-selected active company id. */
export const ACTIVE_COMPANY_KEY = "portal.activeCompanyId";

/** localStorage key for the UI language preference. */
export const LANGUAGE_KEY = "portal.language";

/** OTP code length the backend issues. */
export const OTP_CODE_LENGTH = 6;

/** Default resend cooldown (seconds) when no Retry-After header is present. */
export const OTP_RESEND_FALLBACK_SECONDS = 60;

/** UZ tax_id must be exactly 9 digits. */
export const UZ_TAX_ID_LENGTH = 9;

/** Bank MFO must be exactly 5 digits. */
export const BANK_MFO_LENGTH = 5;

/**
 * Max upload size accepted client-side. MUST mirror the server's
 * `storage_service.MAX_SIZE_BYTES` (10 MB) — when this was larger, oversized
 * files passed the client check, the wizard created the company, and only then
 * did the upload 422 with `file_too_large`, leaving an orphaned draft company.
 */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

/** Human-readable form of {@link MAX_UPLOAD_BYTES}, interpolated into hints/errors. */
export const MAX_UPLOAD_MB = MAX_UPLOAD_BYTES / (1024 * 1024);
