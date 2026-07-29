"use client";

import { useCallback, useState } from "react";
import { setToken, getToken, logoutSession } from "@/lib/api";
import { announceSession } from "@/lib/session";

export interface AuthUser {
  id: number;
  email: string;
  role: string;
}

/**
 * JWT auth hook.
 * Token is stored in memory (setToken / getToken from lib/api.ts).
 * The refresh token lives in an httpOnly cookie managed by the backend.
 * T-04-06: token never echoed to DOM or console.
 */

function parseJwtPayload(token: string): AuthUser | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1]!));
    // JWT subject is the user id (string), role is in payload
    return {
      id: parseInt(payload.sub ?? "0", 10),
      email: payload.email ?? "",
      role: payload.role ?? "viewer",
    };
  } catch {
    return null;
  }
}

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

export function useAuth() {
  const [token, setTokenState] = useState<string | null>(getToken);
  const [user, setUser] = useState<AuthUser | null>(() => {
    const t = getToken();
    return t ? parseJwtPayload(t) : null;
  });

  const login = useCallback((newToken: string) => {
    setToken(newToken);
    setTokenState(newToken);
    const next = parseJwtPayload(newToken);
    setUser(next);
    // The refresh cookie is browser-wide: this sign-in re-points every other open
    // tab at `next`. Say so, so they can warn instead of switching in silence.
    if (next) announceSession({ type: "signin", userId: next.id });
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
    setTokenState(null);
    setUser(null);
    announceSession({ type: "signout" });
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }, []);

  const isAuthenticated =
    token !== null && !isTokenExpired(token);

  return {
    token,
    user,
    role: user?.role ?? null,
    isAuthenticated,
    login,
    logout,
  };
}
