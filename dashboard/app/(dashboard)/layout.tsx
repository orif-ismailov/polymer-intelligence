"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { useAuth } from "@/hooks/useAuth";
import queryClient from "@/lib/queryClient";

/**
 * Auth-guarded route-group layout for all dashboard routes.
 *
 * Security boundary: API's require_role is the real guard (PATTERNS.md Shared Patterns).
 * This layout is UX-layer — redirects to /login on absent/expired JWT.
 *
 * T-04-05: Absent/expired JWT → redirect to /login.
 * Wraps children in QueryClientProvider (TanStack Query singleton).
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (!isAuthenticated) {
      router.push("/login");
    }
  }, [isAuthenticated, router]);

  // While redirecting, render nothing to avoid flash of protected content
  if (!isAuthenticated) {
    return null;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <AppShell>{children}</AppShell>
    </QueryClientProvider>
  );
}
