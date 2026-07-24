import { api } from "@/shared/api";

import type { Account, AccountPatch, AuthResult, OtpVerifyPayload } from "./types";

export const accountApi = {
  requestOtp: (phone: string): Promise<void> =>
    api.post<void>("/portal/auth/otp/request", { phone }),

  verifyOtp: (payload: OtpVerifyPayload): Promise<AuthResult> =>
    api.post<AuthResult>("/portal/auth/otp/verify", payload),

  refresh: (): Promise<AuthResult> => api.post<AuthResult>("/portal/auth/refresh"),

  logout: (): Promise<{ ok: boolean }> => api.post<{ ok: boolean }>("/portal/auth/logout"),

  me: (): Promise<Account> => api.get<Account>("/portal/me"),

  updateMe: (patch: AccountPatch): Promise<Account> =>
    api.patch<Account>("/portal/me", patch),

  /** Dev/e2e helper — reads the last OTP for a phone. Not used in production. */
  peekOtp: (phone: string): Promise<{ code: string }> =>
    api.get<{ code: string }>("/portal/auth/otp/peek", { query: { phone } }),
};

export const accountKeys = {
  me: ["account", "me"] as const,
};
