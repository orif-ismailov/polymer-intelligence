"use client";

import { useCallback, useState } from "react";
import { setToken, getToken } from "@/lib/api";

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
    if (!payload.exp) return false;
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
    setUser(parseJwtPayload(newToken));
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setTokenState(null);
    setUser(null);
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
