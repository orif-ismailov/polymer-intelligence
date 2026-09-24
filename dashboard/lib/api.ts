/**
 * Typed fetch wrapper for the Polymer Intelligence API.
 *
 * - Prefixes /api/v1
 * - Attaches Authorization: Bearer <token> from the in-memory token store
 * - Parses JSON responses
 * - On 401 redirects to /login (T-04-06: token never echoed to DOM/logs)
 */

import { routing } from "@/i18n/routing";

const API_BASE = "/api/v1";

/**
 * Split `/ru/deals` into its locale and the rest.
 *
 * Needed because the redirect below is a raw `window.location` assignment — it
 * has no access to next-intl's locale-aware router — and dropping the prefix
 * sent a person working in `uz` to the Russian login screen.
 */
function splitLocale(pathname: string): { locale: string; rest: string } {
  const [, first = "", ...tail] = pathname.split("/");
  if ((routing.locales as readonly string[]).includes(first)) {
    return { locale: first, rest: `/${tail.join("/")}` };
  }
  return { locale: routing.defaultLocale, rest: pathname };
}

/**
 * Is this a path we are willing to send someone to after they sign in?
 *
 * Only an app-internal absolute path. `//evil.com` is a protocol-relative URL
 * the browser treats as another origin, so the leading-slash check alone is an
 * open redirect — and this value arrives from the query string, which anyone
 * can write.
 */
export function isSafeNext(value: string | null | undefined): value is string {
  return (
    !!value &&
    value.startsWith("/") &&
    !value.startsWith("//") &&
    !value.includes("\\")
  );
}

/**
 * The session is gone — send them to sign in, remembering where they were.
 *
 * Two things this must not lose, and used to lose both (IMEX-21): the locale,
 * and the page that was asked for. `next` is stored WITHOUT the locale prefix
 * so the login page can hand it straight to next-intl's router, which adds the
 * prefix back for whatever locale the person is actually in.
 */
function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  const { locale, rest } = splitLocale(window.location.pathname);
  const next = `${rest}${window.location.search}`;
  const base = `/${locale}/login`;
  window.location.href =
    isSafeNext(next) && !rest.startsWith("/login")
      ? `${base}?next=${encodeURIComponent(next)}`
      : base;
}

// In-memory token store. The token is written by useAuth on login
// and cleared on logout. Never placed in localStorage (XSS risk).
let _inMemoryToken: string | null = null;

export function setToken(token: string | null): void {
  _inMemoryToken = token;
}

export function getToken(): string | null {
  return _inMemoryToken;
}

/**
 * Silently mint a fresh access token from the httpOnly refresh cookie.
 *
 * The access token lives only in memory (XSS-safe) and is therefore lost on a
 * full page reload or when navigating directly to a protected URL. The backend
 * issues a 7-day httpOnly refresh cookie at login (path=/api/v1/auth); this
 * exchanges it for a new 15-min access token via POST /auth/refresh.
 *
 * Uses a raw fetch (not apiFetch) so a 401 here does NOT trigger the global
 * redirect-to-login side effect — the caller decides what to do on failure.
 * Returns the new access token on success, or null when there is no valid
 * refresh cookie (caller should then redirect to /login).
 */
export async function refreshAccessToken(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { access_token?: string };
    if (!data.access_token) return null;
    setToken(data.access_token);
    return data.access_token;
  } catch {
    return null;
  }
}

/**
 * End the session server-side: POST /auth/logout clears the httpOnly refresh
 * cookie, then the in-memory access token is dropped.
 *
 * Clearing the token alone would not be a logout — the 7-day refresh cookie
 * silently re-authenticates on the next page load, so closing the tab never
 * ended the session. Best-effort on the network call: if it fails the cookie may
 * survive, but this tab is signed out either way and the caller redirects to
 * /login rather than pretending nothing happened.
 */
export async function logoutSession(): Promise<void> {
  try {
    await fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "include" });
  } catch {
    // Network failure — nothing to report; the token is dropped regardless.
  }
  setToken(null);
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiFetchOptions {
  /**
   * Handle a 401 by redirecting to the login screen. Default `true`.
   *
   * Pass `false` wherever a 401 is an ANSWER rather than an expired session.
   * `/auth/login` is the case that mattered: a wrong password is a 401, so the
   * global redirect tore the login page down mid-navigation and the `catch` that
   * would have rendered «Email yoki parol noto'g'ri» never got to paint. The
   * user saw the screen blink and both fields empty, with nothing said
   * (IMEX-17). `refreshAccessToken` and `logoutSession` already dodge this by
   * using raw `fetch`; this is the same exemption, made available to callers
   * that want the rest of `apiFetch`.
   */
  redirectOnUnauthorized?: boolean;
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
  options?: ApiFetchOptions,
): Promise<T> {
  const token = getToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

  const response = await fetch(url, {
    ...init,
    headers,
    // Send/receive the httpOnly refresh cookie (login sets it; refresh reads it).
    credentials: "include",
  });

  if (response.status === 401 && options?.redirectOnUnauthorized !== false) {
    // Token absent or expired — redirect to login (T-04-06: no token echo)
    redirectToLogin();
    throw new ApiError(401, null, "Unauthorized — redirecting to login");
  }

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // ignore parse failure on error responses
    }
    throw new ApiError(
      response.status,
      body,
      `API request failed: ${response.status} ${response.statusText}`,
    );
  }

  // 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

/**
 * Authenticated GET returning the raw body as a Blob — an image or file behind a
 * staff route. An `<img src>` cannot carry the Bearer token, so a protected
 * picture (a technologist's portrait under review) is fetched here and shown
 * through an object URL.
 */
export async function apiBlob(path: string): Promise<Blob> {
  const token = getToken();
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const response = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
  });
  if (response.status === 401) {
    redirectToLogin();
    throw new ApiError(401, null, "Unauthorized — redirecting to login");
  }
  if (!response.ok) {
    throw new ApiError(response.status, null, `API request failed: ${response.status}`);
  }
  return response.blob();
}

/**
 * Multipart upload (P6 — the lab-result PDF).
 *
 * Separate from `apiFetch` because that one always sets
 * `Content-Type: application/json`; on a FormData body the browser must set the
 * header itself so it can add the multipart boundary. Overriding it by hand
 * produces a request the server cannot parse.
 */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const response = await fetch(url, {
    method: "POST",
    body: form,
    headers,
    credentials: "include",
  });

  if (response.status === 401) {
    redirectToLogin();
    throw new ApiError(401, null, "Unauthorized — redirecting to login");
  }
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // ignore parse failure on error responses
    }
    throw new ApiError(
      response.status,
      body,
      `API request failed: ${response.status} ${response.statusText}`,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
