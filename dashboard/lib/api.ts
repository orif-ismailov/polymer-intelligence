/**
 * Typed fetch wrapper for the Polymer Intelligence API.
 *
 * - Prefixes /api/v1
 * - Attaches Authorization: Bearer <token> from the in-memory token store
 * - Parses JSON responses
 * - On 401 redirects to /login (T-04-06: token never echoed to DOM/logs)
 */

const API_BASE = "/api/v1";

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

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
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

  if (response.status === 401) {
    // Token absent or expired — redirect to login (T-04-06: no token echo)
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
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
    if (typeof window !== "undefined") window.location.href = "/login";
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
