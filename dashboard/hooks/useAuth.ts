"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { setToken, getToken, logoutSession, apiFetch } from "@/lib/api";
import { announceSession } from "@/lib/session";

export type AccessLevel = "read" | "write";

export interface AuthUser {
  id: number;
  email: string;
  full_name: string;
  is_admin: boolean;
  /** Every page this account can reach, as `{page: "read" | "write"}`. */
  access: Record<string, AccessLevel>;
}

/**
 * JWT auth hook.
 * Token is stored in memory (setToken / getToken from lib/api.ts).
 * The refresh token lives in an httpOnly cookie managed by the backend.
 * T-04-06: token never echoed to DOM or console.
 *
 * Identity comes from GET /auth/me, not from decoding the token. The access
 * token deliberately carries no authorization claim, so that demoting or
 * deactivating someone takes effect on their next request rather than when
 * their 15-minute token happens to expire.
 */

function isTokenExpired(token: string): boolean {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return true;
    const payload = JSON.parse(atob(parts[1]!));
    if (!payload.exp) return true;  // WR-07: no exp claim = treat as expired (fail-closed)
    // exp is seconds since epoch
    return Date.now() / 1000 > payload.exp;
  } catch {
    return true;
  }
}

// ── Shared /auth/me request ──────────────────────────────────────────────────
//
// useAuth() is called by ~18 components, and each one used to decode the token
// locally for free. Now that identity comes from the server, an unshared fetch
// per caller meant six requests for one page load. Callers holding the same
// token share a single in-flight promise instead.
//
// Keyed by the token, so a new sign-in (which always mints a new one) bypasses
// the cache rather than resurrecting the previous account's identity. Not
// TanStack Query: its provider wraps only the (dashboard) route group, and the
// login page calls this hook from outside it.
let _meToken: string | null = null;
let _mePromise: Promise<AuthUser> | null = null;

function fetchMe(token: string): Promise<AuthUser> {
  if (token !== _meToken || _mePromise === null) {
    _meToken = token;
    _mePromise = apiFetch<AuthUser>("/auth/me");
  }
  return _mePromise;
}

function clearMe(): void {
  _meToken = null;
  _mePromise = null;
}

export function useAuth() {
  const [token, setTokenState] = useState<string | null>(getToken);
  const [fetchedUser, setFetchedUser] = useState<AuthUser | null>(null);
  // Set by login() so the effect below can tell a fresh sign-in from a reload,
  // and announce only the former to the other tabs.
  const signingIn = useRef(false);

  // Resolve identity whenever we hold a token — including after a reload, where
  // the token was silently re-minted from the refresh cookie and carries nothing
  // but a subject.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    fetchMe(token)
      .then((me) => {
        if (cancelled) return;
        setFetchedUser(me);
        if (signingIn.current) {
          signingIn.current = false;
          // The refresh cookie is browser-wide: this sign-in re-points every
          // other open tab at `me`. Say so, so they can warn instead of
          // switching in silence.
          announceSession({ type: "signin", userId: me.id });
        }
      })
      .catch(() => {
        if (!cancelled) setFetchedUser(null);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Derived, not stored: dropping the token must revoke the identity in the same
  // render, without an effect racing the components that read it.
  const user = token ? fetchedUser : null;

  const login = useCallback((newToken: string) => {
    signingIn.current = true;
    setToken(newToken);
    setTokenState(newToken);
  }, []);

  /**
   * End the session everywhere, not just in this tab.
   *
   * Revoking the refresh cookie server-side is the part that matters: the access
   * token is in memory only, so without it "logging out" would leave a 7-day
   * silent re-auth sitting on the workstation. The redirect happens either way.
   */
  const logout = useCallback(async () => {
    await logoutSession();
    clearMe();
    setTokenState(null);
    setFetchedUser(null);
    announceSession({ type: "signout" });
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }, []);

  const isAuthenticated =
    token !== null && !isTokenExpired(token);

  /**
   * Whether this account may reach `page` at `level`.
   *
   * `write` implies `read`, mirroring the backend's `pages.satisfies` — the two
   * must agree or the UI offers a button the API refuses. This decides what to
   * RENDER; it is not the boundary. Every request is re-checked server-side.
   *
   * Returns false while /auth/me is still in flight, so a page never flashes
   * before we know whether it should.
   */
  const can = useCallback(
    (page: string, level: AccessLevel = "read"): boolean => {
      const granted = user?.access?.[page];
      if (!granted) return false;
      return granted === "write" || level === "read";
    },
    [user],
  );

  return {
    token,
    user,
    isAdmin: user?.is_admin ?? false,
    access: user?.access ?? {},
    can,
    isAuthenticated,
    login,
    logout,
  };
}
