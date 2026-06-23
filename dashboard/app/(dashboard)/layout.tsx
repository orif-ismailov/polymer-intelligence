"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { refreshAccessToken } from "@/lib/api";
import queryClient from "@/lib/queryClient";

/**
 * Auth-guarded route-group layout for all dashboard routes.
 *
 * Security boundary: API's require_role is the real guard (PATTERNS.md Shared Patterns).
 * This layout is UX-layer.
 *
 * The access token lives only in memory, so a full reload / direct navigation
 * starts unauthenticated. Before bouncing to /login we attempt a silent refresh
 * from the httpOnly refresh cookie (T-04-05 / DEC-auth-split) — only redirect if
 * that fails. Wraps children in QueryClientProvider (TanStack Query singleton).
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isAuthenticated, login } = useAuth();
  // True until we know whether the user is authenticated (incl. a refresh attempt).
  const [checking, setChecking] = useState(!isAuthenticated);

  useEffect(() => {
    if (isAuthenticated) {
      setChecking(false);
      return;
    }
    let cancelled = false;
    (async () => {
      const token = await refreshAccessToken();
      if (cancelled) return;
      if (token) {
        login(token);
      } else {
        router.replace("/login");
      }
      setChecking(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, login, router]);

  // While verifying (or redirecting), render nothing to avoid a flash of
  // protected content or a premature login bounce.
  if (checking || !isAuthenticated) {
    return null;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <AppShell>{children}</AppShell>
    </QueryClientProvider>
  );
}
