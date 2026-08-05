import { api } from "@/shared/api";

import type { Account, AccountPatch, AuthResult, OtpVerifyPayload } from "./types";

export const accountApi = {
  requestOtp: (phone: string): Promise<void> =>
    api.post<void>("/portal/auth/otp/request", { phone }),

  verifyOtp: (payload: OtpVerifyPayload): Promise<AuthResult> =>
    api.post<AuthResult>("/portal/auth/otp/verify", payload),

  // `skipAuthRetry`: this IS the refresh. Without it a 401 here sent the client
  // into its own 401-handler, which refreshed again, failed again, and then
  // hard-redirected to /login — three requests to answer "no session". Harmless
  // while every page was behind the login; on the public marketplace it threw
  // anonymous visitors off the storefront on first paint.
  refresh: (): Promise<AuthResult> =>
    api.post<AuthResult>("/portal/auth/refresh", undefined, { skipAuthRetry: true }),

  logout: (): Promise<{ ok: boolean }> => api.post<{ ok: boolean }>("/portal/auth/logout"),

  me: (): Promise<Account> => api.get<Account>("/portal/me"),

  updateMe: (patch: AccountPatch): Promise<Account> =>
    api.patch<Account>("/portal/me", patch),
};

// NOTE: there is deliberately no `peekOtp` here. The backend does expose
// `GET /portal/auth/otp/peek` as a test hook, but it is double-gated (404 unless
// DEBUG *and* the console SMS driver) and nothing in the app or the e2e suite
// called the client wrapper — it only shipped the endpoint's name inside the
// production bundle. The e2e specs read the code from the API directly.

export const accountKeys = {
  me: ["account", "me"] as const,
};
