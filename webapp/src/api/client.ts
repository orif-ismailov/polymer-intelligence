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
  AuthConfig,
  CatalogOffer,
  CategoryCount,
  ClientProfile,
  ClientProfilePatch,
  FeaturedOffer,
  NewsItem,
  NewsSummary,
  OfferRequestCreate,
  OfferRequestOut,
  OfferRequestUpdate,
  Product,
  RequestCreate,
  RequestDetail,
  RequestFileMeta,
  RequestOut,
  SellerOfferCreate,
  SellerOfferOut,
  TelegramLoginPayload,
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
  // Mini App: send the initData HMAC header. Browser: initData is "" — omit the header
  // so the backend falls through to the httpOnly client_session cookie instead.
  const initData = getInitData();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    // Send the client_session cookie on the browser auth path (same-origin behind nginx).
    credentials: "include",
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(initData ? { "X-Telegram-Init-Data": initData } : {}),
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
  // ── Browser auth (Telegram Login Widget) ────────────────────────────────────

  /** GET /webapp/auth/config — public: the bot @handle for the Login Widget. */
  getAuthConfig(): Promise<AuthConfig> {
    return apiFetch<AuthConfig>("/webapp/auth/config");
  },

  /** POST /webapp/auth/telegram — verify a widget payload; sets the session cookie. */
  loginTelegram(payload: TelegramLoginPayload): Promise<{ ok: boolean }> {
    return apiFetch<{ ok: boolean }>("/webapp/auth/telegram", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /** POST /webapp/auth/logout — clear the browser session cookie. */
  logout(): Promise<{ ok: boolean }> {
    return apiFetch<{ ok: boolean }>("/webapp/auth/logout", { method: "POST" });
  },

  /** GET /webapp/market/featured — public featured offers for the landing (no contacts). */
  getFeaturedOffers(): Promise<FeaturedOffer[]> {
    return apiFetch<FeaturedOffer[]>("/webapp/market/featured");
  },

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

  /**
   * GET /webapp/requests/{id}/files/{fileId} — owner-only file bytes (image/PDF/…).
   * Returned as a Blob so the caller can render an image inline or open/download it.
   * Uses a raw fetch (not apiFetch) because the response is binary, not JSON.
   */
  async getRequestFile(requestId: number, fileId: number): Promise<Blob> {
    const initData = getInitData();
    const res = await fetch(`${BASE_URL}/webapp/requests/${requestId}/files/${fileId}`, {
      credentials: "include",
      headers: initData ? { "X-Telegram-Init-Data": initData } : {},
    });
    if (!res.ok) throw new ApiError(res.status, "file fetch failed");
    return res.blob();
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

  /** GET /webapp/reference/products — active polymer products for the selectors. */
  getProducts(): Promise<Product[]> {
    return apiFetch<Product[]>("/webapp/reference/products");
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

  /**
   * POST /webapp/market/offers/{id}/request — "Request an offer": a buyer inquiry
   * that goes to admin review, then (if approved) to the seller.
   */
  requestOffer(offerId: number, body: OfferRequestCreate): Promise<OfferRequestOut> {
    return apiFetch<OfferRequestOut>(`/webapp/market/offers/${offerId}/request`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** GET /webapp/market/my-requests — the buyer's own inquiries with status. */
  getMyOfferRequests(): Promise<OfferRequestOut[]> {
    return apiFetch<OfferRequestOut[]>("/webapp/market/my-requests");
  },

  /** GET /webapp/market/my-requests/{id} — one of the buyer's own inquiries. */
  getMyOfferRequest(id: number): Promise<OfferRequestOut> {
    return apiFetch<OfferRequestOut>(`/webapp/market/my-requests/${id}`);
  },

  /**
   * PATCH /webapp/market/my-requests/{id} — edit one's own inquiry (full-replacement
   * body). Records the edit, re-enters review, and notifies the seller of the changes.
   */
  updateOfferRequest(id: number, body: OfferRequestUpdate): Promise<OfferRequestOut> {
    return apiFetch<OfferRequestOut>(`/webapp/market/my-requests/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
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

  /** POST /webapp/seller/offers/{id}/files — attach an image/TDS/cert to an offer. */
  uploadOfferFile(offerId: number, file: File, kind = "image"): Promise<{ id: number }> {
    const fd = new FormData();
    fd.append("file", file);
    return apiFetch<{ id: number }>(`/webapp/seller/offers/${offerId}/files?kind=${kind}`, {
      method: "POST",
      body: fd,
    });
  },

  /**
   * POST /webapp/seller/offers/{id}/submit — finalize after uploads: posts the offer
   * (image + seller details + Confirm button) to the team group for moderation.
   */
  submitSellerOffer(offerId: number): Promise<{ ok: boolean }> {
    return apiFetch<{ ok: boolean }>(`/webapp/seller/offers/${offerId}/submit`, {
      method: "POST",
    });
  },

  /** Public URL for an approved offer's file (usable directly in <img src>). */
  offerImageUrl(offerId: number, fileId: number): string {
    return `${BASE_URL}/webapp/market/offers/${offerId}/images/${fileId}`;
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
