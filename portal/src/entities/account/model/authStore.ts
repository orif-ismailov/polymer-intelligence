import { create } from "zustand";

import { registerAuthBridge } from "@/shared/api";

import type { Account } from "./types";

/**
 * Auth store. The access token lives in memory ONLY — never in localStorage —
 * so an XSS payload can't lift a long-lived credential. Session continuity
 * across reloads is provided by the httpOnly refresh cookie + a boot-time
 * refresh (see `useBootstrapAuth`).
 */
interface AuthState {
  token: string | null;
  account: Account | null;
  /** True until the boot-time refresh attempt resolves. */
  initializing: boolean;
  setAuth: (token: string, account: Account) => void;
  setToken: (token: string) => void;
  setAccount: (account: Account) => void;
  setInitialized: () => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  account: null,
  initializing: true,
  setAuth: (token, account) => set({ token, account }),
  setToken: (token) => set({ token }),
  setAccount: (account) => set({ account }),
  setInitialized: () => set({ initializing: false }),
  clear: () => set({ token: null, account: null }),
}));

// Wire the store into the shared fetch client. This is the single point where
// `shared/api` learns how to read/write/clear auth state without importing this
// module directly (FSD: shared must not depend on entities).
registerAuthBridge({
  getToken: () => useAuthStore.getState().token,
  setToken: (token) => useAuthStore.getState().setToken(token),
  clear: () => useAuthStore.getState().clear(),
});

/** Selector: is the user authenticated (has an access token). */
export const selectIsAuthenticated = (state: AuthState): boolean => state.token !== null;
