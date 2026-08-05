/**
 * Portal fetch client.
 *
 * Contract:
 *  - baseURL `/api/v1`, called same-origin (dev proxy / prod nginx).
 *  - Attaches `Authorization: Bearer <token>` from the in-memory auth bridge.
 *  - `credentials: "include"` so the httpOnly refresh cookie (path
 *    `/api/v1/portal`) travels with requests.
 *  - On a 401 it performs a single silent `POST /portal/auth/refresh`, swaps in
 *    the new token, and retries the original request exactly once. If refresh
 *    fails it clears auth, and hard-navigates to `/cabinet/login` ONLY from a page that
 *    requires a session — never from the public marketplace, where being signed
 *    out is the normal state.
 *
 * The refresh is de-duplicated: concurrent 401s share one in-flight refresh.
 */

import { API_BASE, isCabinetPath, SERVER_API_ORIGIN } from "@/shared/config";

import { clearAuth, getAuthToken, setAuthToken } from "./authBridge";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly detail: unknown;
  readonly retryAfterSeconds: number | null;

  constructor(
    status: number,
    message: string,
    options: {
      code?: string | null;
      detail?: unknown;
      retryAfterSeconds?: number | null;
    } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = options.code ?? null;
    this.detail = options.detail ?? null;
    this.retryAfterSeconds = options.retryAfterSeconds ?? null;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Query;
  /** Skip the automatic 401→refresh→retry cycle (used by refresh itself). */
  skipAuthRetry?: boolean;
  signal?: AbortSignal;
}

const REFRESH_PATH = "/portal/auth/refresh";

function buildUrl(path: string, query?: Query): string {
  // `SERVER_API_ORIGIN` is "" in the browser, so this is the same relative URL
  // it has always been there; under SSR it becomes the internal API address,
  // because Node cannot resolve a root-relative URL on its own.
  const url = `${SERVER_API_ORIGIN}${API_BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) continue;
    params.append(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

function parseRetryAfter(headers: Headers): number | null {
  const raw = headers.get("Retry-After");
  if (!raw) return null;
  const seconds = Number(raw);
  return Number.isFinite(seconds) ? seconds : null;
}

interface RawErrorBody {
  detail?: unknown;
  message?: string;
}

function extractError(status: number, body: unknown, headers: Headers): ApiError {
  const retryAfterSeconds = parseRetryAfter(headers);
  let message = `Request failed with status ${status}`;
  let code: string | null = null;

  if (body && typeof body === "object") {
    const { detail, message: msg } = body as RawErrorBody;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      const detailObj = detail as { code?: unknown; message?: unknown };
      if (typeof detailObj.code === "string") code = detailObj.code;
      if (typeof detailObj.message === "string") message = detailObj.message;
    } else if (typeof msg === "string") {
      message = msg;
    }
  }

  return new ApiError(status, message, { code, detail: body, retryAfterSeconds });
}

async function readBody(res: Response): Promise<unknown> {
  if (res.status === 204 || res.status === 205) return undefined;
  const contentType = res.headers.get("Content-Type") ?? "";
  if (contentType.includes("application/json")) {
    return (await res.json()) as unknown;
  }
  const text = await res.text();
  return text === "" ? undefined : text;
}

// ── Single-flight refresh ────────────────────────────────────────────────────

let refreshInFlight: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  const res = await fetch(buildUrl(REFRESH_PATH), {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) return false;
  const body = (await readBody(res)) as { access_token?: unknown } | undefined;
  const token = body?.access_token;
  if (typeof token !== "string" || token === "") return false;
  setAuthToken(token);
  return true;
}

function refreshOnce(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/**
 * Clear the session, and bounce to /login only from a page that needs one.
 *
 * A 401 means "you are not signed in". On a cabinet screen that is a dead end
 * and the login form is the answer. On the public marketplace it is the normal
 * state of most visitors, and navigating them away from the storefront because a
 * background call needed a session would be a bug they experience as the site
 * kicking them out.
 *
 * The test is "am I inside the cabinet", not "am I on a known public page".
 * Those are not the same question: the old whitelist also bounced `/dev/ui` and
 * every 404, because anything it did not recognise looked authenticated to it.
 */
function redirectToLogin(): void {
  clearAuth();
  if (typeof window === "undefined") return;

  const path = window.location.pathname;
  if (path === "/cabinet/login" || !isCabinetPath(path)) return;

  window.location.assign("/cabinet/login");
}

// ── Core ─────────────────────────────────────────────────────────────────────

async function rawRequest(
  path: string,
  init: RequestInit,
  query?: Query,
): Promise<Response> {
  const token = getAuthToken();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  return fetch(buildUrl(path, query), {
    ...init,
    headers,
    credentials: "include",
  });
}

function isNetworkFailure(err: unknown): boolean {
  // Chromium: TypeError "Failed to fetch"; Safari/Firefox vary. Aborts stay aborts.
  if (err instanceof DOMException && err.name === "AbortError") return false;
  if (err instanceof TypeError) return true;
  return err instanceof Error && /failed to fetch|networkerror|load failed/i.test(err.message);
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, skipAuthRetry = false, signal } = options;

  const init: RequestInit = { method, signal };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }

  let res: Response;
  try {
    res = await rawRequest(path, init, query);
  } catch (err) {
    if (isNetworkFailure(err)) {
      throw new ApiError(0, "Network error", { code: "network" });
    }
    throw err;
  }

  if (res.status === 401 && !skipAuthRetry) {
    const refreshed = await refreshOnce();
    if (!refreshed) {
      redirectToLogin();
      throw extractError(401, await readBody(res), res.headers);
    }
    try {
      res = await rawRequest(path, init, query);
    } catch (err) {
      if (isNetworkFailure(err)) {
        throw new ApiError(0, "Network error", { code: "network" });
      }
      throw err;
    }
    if (res.status === 401) {
      redirectToLogin();
      throw extractError(401, await readBody(res), res.headers);
    }
  }

  const parsed = await readBody(res);
  if (!res.ok) {
    throw extractError(res.status, parsed, res.headers);
  }
  return parsed as T;
}

// ── Public verb helpers ──────────────────────────────────────────────────────

export const api = {
  get: <T>(path: string, opts?: Pick<RequestOptions, "query" | "signal">): Promise<T> =>
    request<T>(path, { method: "GET", ...opts }),

  post: <T>(
    path: string,
    body?: unknown,
    opts?: Pick<RequestOptions, "query" | "signal" | "skipAuthRetry">,
  ): Promise<T> => request<T>(path, { method: "POST", body, ...opts }),

  patch: <T>(path: string, body?: unknown, opts?: Pick<RequestOptions, "query">): Promise<T> =>
    request<T>(path, { method: "PATCH", body, ...opts }),

  put: <T>(path: string, body?: unknown, opts?: Pick<RequestOptions, "query">): Promise<T> =>
    request<T>(path, { method: "PUT", body, ...opts }),

  del: <T>(path: string, opts?: Pick<RequestOptions, "query">): Promise<T> =>
    request<T>(path, { method: "DELETE", ...opts }),

  /** Multipart upload; the browser sets the boundary Content-Type itself. */
  upload: <T>(path: string, form: FormData): Promise<T> =>
    request<T>(path, { method: "POST", body: form }),

  /** Authenticated GET returning the raw body as a Blob (dynamic downloads, e.g. zip). */
  blob: async (path: string): Promise<Blob> => {
    let res = await rawRequest(path, { method: "GET" });
    if (res.status === 401) {
      const refreshed = await refreshOnce();
      if (refreshed) res = await rawRequest(path, { method: "GET" });
    }
    if (!res.ok) throw extractError(res.status, await readBody(res), res.headers);
    return res.blob();
  },
};

/**
 * Build an authenticated download URL. The presigned redirect (307) needs the
 * bearer token — but a plain <a href> can't set headers. We resolve the redirect
 * programmatically and hand back the final presigned location.
 */
export async function resolveDownloadUrl(path: string): Promise<string> {
  const res = await rawRequest(path, { method: "GET", redirect: "manual" });
  // Opaque redirect (browser followed it) — the response URL is the target.
  if (res.type === "opaqueredirect") {
    return res.url;
  }
  const location = res.headers.get("Location");
  if (location) return location;
  // Some proxies auto-follow; fall back to the resolved URL.
  return res.url;
}
