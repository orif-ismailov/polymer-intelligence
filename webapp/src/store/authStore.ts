/**
 * authStore — dual-context authentication state (Telegram Mini App + browser).
 *
 * Mini App: identity comes from initData on every request, so the user is always
 * authenticated — no login gate. Browser: the user must sign in via the Telegram
 * Login Widget, which sets an httpOnly client_session cookie; we probe GET /webapp/me
 * once at boot to learn whether that cookie is present/valid.
 *
 *   status: 'loading' → resolving auth at boot (avoid a gate flash)
 *           'authed'  → identity established (Mini App always; browser after login)
 *           'anon'    → browser visitor without a valid session
 */

import { create } from "zustand";

import { api } from "../api/client";
import { isMiniApp } from "../telegram";
import type { ClientProfile } from "../types";

export type AuthStatus = "loading" | "authed" | "anon";

interface AuthState {
  status: AuthStatus;
  isMiniApp: boolean;
  profile: ClientProfile | null;
  /** Resolve auth once at boot. Idempotent. */
  bootstrap: () => Promise<void>;
  /** Mark authenticated after a successful browser login (widget → cookie set). */
  markAuthed: (profile?: ClientProfile | null) => void;
  /** Browser sign-out: clear the cookie server-side and reset to anon. */
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  status: "loading",
  isMiniApp: isMiniApp(),
  profile: null,

  bootstrap: async () => {
    if (get().status === "authed") return;

    // Mini App: initData carries identity — authenticated by definition.
    if (isMiniApp()) {
      set({ status: "authed" });
      try {
        set({ profile: await api.getMe() });
      } catch {
        /* profile is best-effort; identity is still valid via initData */
      }
      return;
    }

    // Browser: probe the session cookie via /webapp/me.
    try {
      const profile = await api.getMe();
      set({ status: "authed", profile });
    } catch {
      set({ status: "anon", profile: null });
    }
  },

  markAuthed: (profile = null) => set({ status: "authed", profile }),

  logout: async () => {
    try {
      await api.logout();
    } catch {
      /* best-effort — reset local state regardless */
    }
    set({ status: "anon", profile: null });
  },
}));
