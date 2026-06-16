/**
 * Telegram-initData-authed API client for the Polymer Intelligence Web App.
 *
 * Every request (including multipart file uploads) attaches the
 * X-Telegram-Init-Data header so the backend can verify the caller's identity
 * (T-03-15 mitigation, REQ-webapp-auth).
 *
 * BASE_URL "/api/v1" — the Vite proxy forwards to :8000 in dev.
 */

import { getInitData } from "../telegram";
import type {
  ClientProfile,
  ClientProfilePatch,
  RequestCreate,
  RequestDetail,
  RequestOut,
} from "../types";

const BASE_URL = "/api/v1";

// ── Error type ─────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`ApiError ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

// ── Core fetch wrapper ─────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData(),
      // Spread caller headers AFTER defaults so caller can override Content-Type
      // (e.g. multipart — see uploadFile below which passes its own headers)
      ...options.headers,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new ApiError(res.status, err.detail ?? "Unknown error");
  }

  return res.json() as Promise<T>;
}

// ── API surface ────────────────────────────────────────────────────────────────

export const api = {
  // ── Requests ──────────────────────────────────────────────────────────────

  /** POST /webapp/requests — create a new purchase request. Returns RequestOut with REQ number. */
  createRequest(body: RequestCreate): Promise<RequestOut> {
    return apiFetch<RequestOut>("/webapp/requests", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** GET /webapp/requests — list the authenticated client's requests. */
  getRequests(): Promise<RequestOut[]> {
    return apiFetch<RequestOut[]>("/webapp/requests");
  },

  /** GET /webapp/requests/{id} — detail view with files and status history. */
  getRequest(id: number): Promise<RequestDetail> {
    return apiFetch<RequestDetail>(`/webapp/requests/${id}`);
  },

  /**
   * POST /webapp/requests/{id}/files — multipart file upload.
   *
   * IMPORTANT: Do NOT set Content-Type — the browser must set it with the
   * multipart boundary. We send only the X-Telegram-Init-Data header.
   *
   * Uploads are sequential (called one at a time by Confirm.tsx) per D-01.
   */
  uploadFile(requestId: number, file: File): Promise<void> {
    const formData = new FormData();
    formData.append("file", file);

    return apiFetch<void>(`/webapp/requests/${requestId}/files`, {
      method: "POST",
      body: formData,
      headers: {
        // Override to remove Content-Type so the browser sets the multipart boundary.
        // X-Telegram-Init-Data is still injected inside apiFetch via the spread.
        // We intentionally omit "Content-Type" by passing only the auth header here.
        "X-Telegram-Init-Data": getInitData(),
      },
    });
  },

  // ── Profile ───────────────────────────────────────────────────────────────

  /** GET /webapp/me — authenticated client's profile. */
  getMe(): Promise<ClientProfile> {
    return apiFetch<ClientProfile>("/webapp/me");
  },

  /** PATCH /webapp/me — update language, company_name, or contact_name. */
  patchMe(body: ClientProfilePatch): Promise<ClientProfile> {
    return apiFetch<ClientProfile>("/webapp/me", {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
};
