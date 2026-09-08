import { api } from "@/shared/api";

import type {
  Account,
  AccountPatch,
  AuthResult,
  LoginPayload,
  PasswordChangePayload,
  RegisterPayload,
} from "./types";

export const accountApi = {
  login: (payload: LoginPayload): Promise<AuthResult> =>
    api.post<AuthResult>("/portal/auth/login", payload),

  /**
   * Ask for access. Answers 202 with a fixed body whatever happens — including for
   * a phone that has applied before — so nothing here can be used to find out who
   * already has an account.
   */
  register: (payload: RegisterPayload): Promise<{ status: string }> =>
    api.post<{ status: string }>("/portal/auth/register", payload),

  /** The only route past the first-login gate; returns a fresh session. */
  changePassword: (payload: PasswordChangePayload): Promise<AuthResult> =>
    api.post<AuthResult>("/portal/auth/password", payload),

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

export const accountKeys = {
  me: ["account", "me"] as const,
};
