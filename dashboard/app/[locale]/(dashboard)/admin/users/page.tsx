"use client";

/**
 * Admin Users page (/admin/users)
 *
 * Admin-only table from GET /admin/users:
 * name, email, role badge (admin=accent/analyst=blue/trader=amber/viewer=muted),
 * created_at.
 *
 * Security (T-04-32): reads /admin/users which excludes password_hash (04-04).
 * Non-admin: redirects to dashboard home (UI gate; backend require_admin is the boundary).
 *
 * No hardcoded hex.
 */

import { Suspense, useEffect } from "react";
import { useRouter } from "@/i18n/navigation";
import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

// ─── Types ─────────────────────────────────────────────────────────────────────

interface StaffUserItem {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

// ─── Role badge ────────────────────────────────────────────────────────────────

// Role badge colors: admin=accent, analyst=blue(status-new), trader=amber(urgency-medium), viewer=muted
const ROLE_CLASSES: Record<string, string> = {
  admin: "text-accent border-accent/50",
  analyst: "text-status-new border-status-new/50",
  trader: "text-urgency-medium border-urgency-medium/50",
  viewer: "text-foreground-muted border-foreground-muted/50",
};

function RoleBadge({ role }: { role: string }) {
  const t = useTranslations("admin");
  const cls = ROLE_CLASSES[role] ?? "text-foreground-muted border-foreground-muted/50";
  const roleLabels: Record<string, string> = {
    admin: t("roles.admin"),
    analyst: t("roles.analyst"),
    trader: t("roles.trader"),
    viewer: t("roles.viewer"),
  };
  const label = roleLabels[role] ?? role;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${cls}`}
    >
      {label}
    </span>
  );
}

// ─── Users table ─────────────────────────────────────────────────────────────

function UsersTable() {
  const t = useTranslations("admin");
  const { data: users = [], isLoading, error } = useQuery<StaffUserItem[]>({
    queryKey: ["admin-users"],
    queryFn: () => apiFetch<StaffUserItem[]>("/admin/users"),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-12 rounded-lg bg-background-tertiary animate-pulse" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-4 text-sm text-urgency-high">
        {t("loadError")}
      </div>
    );
  }

  if (users.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
        <Users size={32} className="text-foreground-muted" aria-hidden="true" />
        <p className="text-sm text-foreground-muted">{t("empty")}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-background-tertiary">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-semibold text-foreground-muted uppercase tracking-wider">{t("table.email")}</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-foreground-muted uppercase tracking-wider">{t("table.role")}</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-foreground-muted uppercase tracking-wider">{t("table.status")}</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-foreground-muted uppercase tracking-wider">{t("table.createdAt")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {users.map((user) => (
            <tr key={user.id} className="bg-background-secondary hover:bg-background-tertiary transition-colors">
              <td className="px-4 py-3">
                <span className="font-medium text-foreground">{user.email}</span>
              </td>
              <td className="px-4 py-3">
                <RoleBadge role={user.role} />
              </td>
              <td className="px-4 py-3">
                {user.is_active ? (
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold text-accent border border-accent/30">
                    {t("statusActive")}
                  </span>
                ) : (
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold text-foreground-muted border border-border">
                    {t("statusInactive")}
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-foreground-muted">
                <time dateTime={user.created_at} title={user.created_at}>
                  {formatTashkent(user.created_at)}
                </time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

function AdminUsersPageContent() {
  const t = useTranslations("admin");
  const router = useRouter();
  const { role, isAuthenticated } = useAuth();

  // UI gate: redirect non-admin to home. Backend require_admin is the security boundary.
  useEffect(() => {
    if (isAuthenticated && role !== "admin") {
      router.replace("/");
    }
  }, [isAuthenticated, role, router]);

  // Don't render table while redirecting
  if (role && role !== "admin") {
    return null;
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <Users size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("pageTitle")}</h1>
          <p className="text-sm text-foreground-muted mt-0.5">
            {t("pageSubtitle")}
          </p>
        </div>
      </div>

      <UsersTable />
    </div>
  );
}

export default function AdminUsersPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4 p-6">
          <div className="h-8 w-40 rounded bg-background-tertiary animate-pulse" />
          <div className="h-12 rounded bg-background-tertiary animate-pulse" />
          <div className="h-12 rounded bg-background-tertiary animate-pulse" />
        </div>
      }
    >
      <AdminUsersPageContent />
    </Suspense>
  );
}
