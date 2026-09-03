"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "@/i18n/navigation";
import { QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { NoAccessNotice } from "@/components/shared/NoAccessNotice";
import { NoPageAccess } from "@/components/shared/NoPageAccess";
import { RouteGuardFallback } from "@/components/shared/RouteGuardFallback";
import { useAuth } from "@/hooks/useAuth";
import { refreshAccessToken } from "@/lib/api";
import { pageForPath, pageKeyOf } from "@/lib/nav";
import queryClient from "@/lib/queryClient";

/**
 * Auth-guarded route-group layout for all dashboard routes.
 *
 * Security boundary: the API's require_admin is the real guard (PATTERNS.md Shared
 * Patterns). This layout is UX-layer — it decides what to render, never what is allowed.
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
  const pathname = usePathname();
  const { isAuthenticated, isAdmin, user, access, can, login } = useAuth();

  useEffect(() => {
    // Already authenticated — nothing to verify.
    if (isAuthenticated) return;
    let cancelled = false;
    (async () => {
      const token = await refreshAccessToken();
      if (cancelled) return;
      if (token) {
        login(token);
      } else {
        router.replace("/login");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, login, router]);

  // No protected content until authenticated. This avoids a flash of protected
  // content while the silent refresh runs, and avoids a premature /login bounce —
  // the redirect is issued from the effect only after the refresh attempt fails.
  // (Render outcome is children ⟺ isAuthenticated, so no separate "checking"
  // state is needed; that synchronous setState-in-effect was also a render smell.)
  // A spinner rather than `null`: the refresh is a network round-trip, and a black
  // viewport for its duration is indistinguishable from a broken page.
  if (!isAuthenticated) {
    return <RouteGuardFallback />;
  }

  // Signed in, but /auth/me has not answered yet — `user` is null for both
  // "still loading" and "not an admin", so waiting is what keeps a legitimate
  // administrator from being told they have no access for a frame.
  if (!user) {
    return <RouteGuardFallback />;
  }

  // Signed in and known to reach nothing at all. Rendering the shell here would
  // show a nav over a wall of 403s, which reads as an outage rather than as a
  // permission boundary.
  if (!isAdmin && Object.keys(access).length === 0) {
    return <NoAccessNotice />;
  }

  // Per-page gate, resolved from the nav rather than declared in each of the 26
  // page components — one place that cannot be forgotten when a page is added.
  // A path outside the nav (there are none today) renders rather than 404s: the
  // API refuses it anyway, and a blank screen would be the worse guess.
  const navItem = pageForPath(pathname);
  const allowed =
    navItem === null
      ? true
      : navItem.adminOnly
        ? isAdmin
        : can(pageKeyOf(navItem));

  return (
    <QueryClientProvider client={queryClient}>
      <AppShell>
        {allowed ? children : <NoPageAccess />}
      </AppShell>
    </QueryClientProvider>
  );
}
