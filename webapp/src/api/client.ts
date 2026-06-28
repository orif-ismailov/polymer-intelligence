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
  CatalogOffer,
  CategoryCount,
  ClientProfile,
  ClientProfilePatch,
  NewsItem,
  NewsSummary,
  RequestCreate,
  RequestDetail,
  RequestFileMeta,
  RequestOut,
  SellerOfferCreate,
  SellerOfferOut,
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
  // Do NOT set Content-Type for multipart/FormData — the browser must set it
  // together with the multipart boundary. JSON requests keep the default.
  const isFormData = options.body instanceof FormData;
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      "X-Telegram-Init-Data": getInitData(),
      // Spread caller headers last so callers can still override if needed
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
  uploadFile(requestId: number, file: File): Promise<RequestFileMeta> {
    const formData = new FormData();
    formData.append("file", file);

    // apiFetch detects FormData and omits Content-Type so the browser sets the
    // multipart boundary automatically. X-Telegram-Init-Data is injected by apiFetch.
    return apiFetch<RequestFileMeta>(`/webapp/requests/${requestId}/files`, {
      method: "POST",
      body: formData,
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

  // ── Marketplace: public catalog ─────────────────────────────────────────────

  /** GET /webapp/market/offers — approved catalog offers (optional product/text filter). */
  getCatalogOffers(params: { product_id?: number; q?: string } = {}): Promise<CatalogOffer[]> {
    const qs = new URLSearchParams();
    if (params.product_id != null) qs.set("product_id", String(params.product_id));
    if (params.q) qs.set("q", params.q);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<CatalogOffer[]>(`/webapp/market/offers${suffix}`);
  },

  /** GET /webapp/market/offers/{id} — a single approved offer. */
  getCatalogOffer(id: number): Promise<CatalogOffer> {
    return apiFetch<CatalogOffer>(`/webapp/market/offers/${id}`);
  },

  /** GET /webapp/market/categories — category chips with approved-offer counts. */
  getCategories(): Promise<CategoryCount[]> {
    return apiFetch<CategoryCount[]>("/webapp/market/categories");
  },

  // ── Marketplace: seller side ────────────────────────────────────────────────

  /** POST /webapp/seller/offers — publish an offer (→ moderation). */
  createSellerOffer(body: SellerOfferCreate): Promise<SellerOfferOut> {
    return apiFetch<SellerOfferOut>("/webapp/seller/offers", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** GET /webapp/seller/offers — the caller's own offers (any status). */
  getMyOffers(): Promise<SellerOfferOut[]> {
    return apiFetch<SellerOfferOut[]>("/webapp/seller/offers");
  },

  // ── News (published reports) ────────────────────────────────────────────────

  /** GET /webapp/news — published market reports (newest first). */
  getNews(): Promise<NewsSummary[]> {
    return apiFetch<NewsSummary[]>("/webapp/news");
  },

  /** GET /webapp/news/{id} — a single published report (with content). */
  getNewsItem(id: number): Promise<NewsItem> {
    return apiFetch<NewsItem>(`/webapp/news/${id}`);
  },
};
