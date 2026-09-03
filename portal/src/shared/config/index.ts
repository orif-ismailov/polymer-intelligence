export * from "./enums";

export * from "./publicRoutes";

/** Relative base — the SPA calls the API same-origin (dev proxy / prod nginx). */
export const API_BASE = "/api/v1";

/**
 * Origin to prefix onto {@link API_BASE} when a fetch runs OUTSIDE a browser.
 *
 * `fetch("/api/v1/…")` has no meaning in Node: there is no document to resolve
 * the relative URL against, so the SSR render would throw on its first request.
 * In the browser this stays `""` and every call remains same-origin, which is
 * what keeps the httpOnly refresh cookie working and CORS out of the picture.
 *
 * The server value is the INTERNAL address of the API (`http://api:8000` under
 * compose), never the public hostname — the render happens inside the network,
 * so it should not leave it and come back through nginx.
 */
export const SERVER_API_ORIGIN: string =
  typeof window === "undefined"
    ? (globalThis as { __INTERNAL_API_ORIGIN__?: string }).__INTERNAL_API_ORIGIN__ ?? ""
    : "";

/**
 * Public origin the storefront is served from, used to build absolute canonical
 * / og:url / sitemap URLs.
 *
 * Injected by the SSR server from `PUBLIC_SITE_ORIGIN` and read from a global on
 * the client, so moving the marketplace to another domain is one env var and no
 * rebuild. Empty means "derive from the current location", which is right for
 * dev and for a browser-only render.
 */
export function publicSiteOrigin(): string {
  const injected = (globalThis as { __PUBLIC_SITE_ORIGIN__?: string }).__PUBLIC_SITE_ORIGIN__;
  if (injected) return injected.replace(/\/+$/, "");
  if (typeof window !== "undefined") return window.location.origin;
  return "";
}

/** localStorage key for the last-selected active company id. */
export const ACTIVE_COMPANY_KEY = "portal.activeCompanyId";

/** localStorage key for the UI language preference. */
export const LANGUAGE_KEY = "portal.language";

/**
 * localStorage key for the colour-theme preference.
 *
 * Also read by the inline bootstrap script in `index.html` — it sets
 * `data-theme` before first paint to avoid a flash of the wrong theme. Change
 * this constant and that script together.
 */
export const THEME_KEY = "portal.theme";

/**
 * localStorage key for the cabinet rail's collapsed state.
 *
 * Unlike {@link THEME_KEY} this needs no bootstrap script: the cabinet is a
 * shell response (`server.js` sends no markup for it), so the store reads this
 * synchronously on the client before first paint and there is no server render
 * to flash against.
 */
export const RAIL_COLLAPSED_KEY = "portal.railCollapsed";

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
