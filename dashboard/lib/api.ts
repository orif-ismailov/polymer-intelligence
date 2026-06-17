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
