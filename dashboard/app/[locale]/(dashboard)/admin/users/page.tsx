"use client";

/**
 * Staff administration (/admin/users)
 *
 * Where colleagues are created, given access, and cut off. Until this existed,
 * staff accounts could only be created by the seeder and access could only be
 * changed with SQL against production — there was no revocation path at all.
 *
 * Administrator-only, and deliberately not a grantable page: whoever can edit
 * staff accounts can mint an administrator (see backend app/api/admin_users.py).
 * The redirect below is UX; `require_admin` is the boundary.
 *
 * Security (T-04-32): the API never returns password_hash, in either direction.
 *
 * No hardcoded hex.
 */

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  StaffAccessMatrix,
  type AccessMap,
} from "@/components/admin/StaffAccessMatrix";
import { RouteGuardFallback } from "@/components/shared/RouteGuardFallback";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

// ─── Types ─────────────────────────────────────────────────────────────────────

interface StaffUserListItem {
  id: number;
  email: string;
  full_name: string;
  is_admin: boolean;
  is_active: boolean;
  granted_pages: number;
  created_at: string;
}

interface StaffUserDetail extends Omit<StaffUserListItem, "granted_pages"> {
  access: AccessMap;
}

/** Mirrors the backend's `_MIN_PASSWORD_LENGTH`; the API rejects anything shorter. */
const MIN_PASSWORD = 12;

/**
 * Turn an API failure into a sentence in the reader's language.
 *
 * The 409s carry `{code, message}`: the code is what we translate, and the
 * English `message` is only a fallback for a code this build has no string for.
 * Rendering `message` directly put an English sentence on a Russian dashboard —
 * caught in the browser, invisible to types and tests.
 */
function useApiError() {
  const t = useTranslations("admin");
  return (e: unknown, fallback: string): string => {
    if (!(e instanceof ApiError)) return fallback;
    const detail = (e.body as { detail?: unknown })?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const { code, message } = detail as { code?: string; message?: string };
      if (code) {
        const key = `errors.${code}`;
        const translated = t.has(key) ? t(key) : null;
        if (translated) return translated;
      }
      if (message) return message;
    }
    return fallback;
  };
}

// ─── Badges ────────────────────────────────────────────────────────────────────

function AccessBadge({ user }: { user: StaffUserListItem }) {
  const t = useTranslations("admin");
  if (user.is_admin) {
    return (
      <span className="inline-flex items-center rounded-full border border-accent/50 px-2 py-0.5 text-xs font-semibold text-accent">
        {t("accessAdmin")}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full border border-foreground-muted/50 px-2 py-0.5 text-xs font-semibold text-foreground-muted">
      {t("accessPages", { count: user.granted_pages })}
    </span>
  );
}

// ─── Editor ────────────────────────────────────────────────────────────────────

function UserEditor({
  user,
  onClose,
}: {
  user: StaffUserDetail | null; // null = creating
  onClose: () => void;
}) {
  const t = useTranslations("admin");
  const apiError = useApiError();
  const qc = useQueryClient();
  const creating = user === null;

  const [email, setEmail] = useState(user?.email ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(user?.is_admin ?? false);
  const [access, setAccess] = useState<AccessMap>(user?.access ?? {});
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      if (creating) {
        return apiFetch<StaffUserDetail>("/admin/users", {
          method: "POST",
          body: JSON.stringify({
            email,
            full_name: fullName,
            password,
            is_admin: isAdmin,
            access: isAdmin ? {} : access,
          }),
        });
      }
      // Two calls, because they are two different authorities: the flags on the
      // account, and the pages it may reach. Access is skipped for an
      // administrator — the API refuses to store grants for one, since they
      // already hold every page.
      await apiFetch<StaffUserDetail>(`/admin/users/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          full_name: fullName,
          is_admin: isAdmin,
          ...(password ? { password } : {}),
        }),
      });
      if (!isAdmin) {
        await apiFetch<StaffUserDetail>(`/admin/users/${user.id}/access`, {
          method: "PUT",
          body: JSON.stringify({ access }),
        });
      }
      return null;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-users"] });
      onClose();
    },
    onError: (e: unknown) => setError(apiError(e, t("saveError"))),
  });

  const passwordTooShort = password.length > 0 && password.length < MIN_PASSWORD;
  const canSave =
    fullName.trim().length > 0 &&
    (!creating || (email.trim().length > 0 && password.length >= MIN_PASSWORD)) &&
    !passwordTooShort &&
    !save.isPending;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{creating ? t("createTitle") : t("editTitle")}</DialogTitle>
          <DialogDescription>
            {creating ? t("createSubtitle") : user.email}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {creating && (
            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-foreground">{t("fieldEmail")}</span>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="ivan@polymer.uz"
              />
            </label>
          )}

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-foreground">{t("fieldName")}</span>
            <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-foreground">
              {creating ? t("fieldPassword") : t("fieldPasswordReset")}
            </span>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={creating ? "" : t("fieldPasswordKeep")}
            />
            <span className="text-xs text-foreground-muted">
              {t("passwordHint", { min: MIN_PASSWORD })}
            </span>
          </label>

          <label className="flex items-start gap-2.5 rounded-lg border border-border p-3">
            <input
              type="checkbox"
              checked={isAdmin}
              onChange={(e) => setIsAdmin(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-accent"
            />
            <span className="flex flex-col gap-0.5">
              <span className="text-sm font-medium text-foreground">{t("fieldIsAdmin")}</span>
              <span className="text-xs text-foreground-muted">{t("isAdminHint")}</span>
            </span>
          </label>

          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium text-foreground">{t("accessTitle")}</span>
            {isAdmin ? (
              <p className="rounded-lg border border-border bg-background-tertiary p-3 text-sm text-foreground-muted">
                {t("adminHoldsEverything")}
              </p>
            ) : (
              <StaffAccessMatrix value={access} onChange={setAccess} />
            )}
          </div>

          {error && (
            <p className="rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-3 text-sm text-urgency-high">
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={save.isPending}>
            {t("cancel")}
          </Button>
          <Button
            onClick={() => {
              setError(null);
              save.mutate();
            }}
            disabled={!canSave}
          >
            {save.isPending ? t("saving") : t("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Table ─────────────────────────────────────────────────────────────────────

function UsersTable() {
  const t = useTranslations("admin");
  const apiError = useApiError();
  const qc = useQueryClient();
  const { user: me } = useAuth();
  const [editing, setEditing] = useState<StaffUserDetail | null | undefined>(undefined);
  const [rowError, setRowError] = useState<string | null>(null);

  const { data: users = [], isLoading, error } = useQuery<StaffUserListItem[]>({
    queryKey: ["admin-users"],
    queryFn: () => apiFetch<StaffUserListItem[]>("/admin/users"),
  });

  const toggleActive = useMutation({
    mutationFn: (u: StaffUserListItem) =>
      apiFetch<StaffUserDetail>(
        `/admin/users/${u.id}/${u.is_active ? "deactivate" : "activate"}`,
        { method: "POST" },
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (e: unknown) => setRowError(apiError(e, t("saveError"))),
  });

  async function openEditor(u: StaffUserListItem) {
    // The list carries a count, not the map — fetch the detail so the matrix
    // opens on what is actually stored rather than on an empty grid.
    setEditing(await apiFetch<StaffUserDetail>(`/admin/users/${u.id}`));
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-12 animate-pulse rounded-lg bg-background-tertiary" />
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

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-sm text-foreground-muted">
          {t("countLabel", { count: users.length })}
        </p>
        <Button onClick={() => setEditing(null)}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t("createButton")}
        </Button>
      </div>

      {rowError && (
        <div className="mb-3 rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-3 text-sm text-urgency-high">
          {rowError}
        </div>
      )}

      {users.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <Users size={32} className="text-foreground-muted" aria-hidden="true" />
          <p className="text-sm text-foreground-muted">{t("empty")}</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-tertiary">
              <tr>
                {["email", "name", "access", "status", "createdAt"].map((c) => (
                  <th
                    key={c}
                    className="px-4 py-3 text-start text-xs font-semibold uppercase tracking-wider text-foreground-muted"
                  >
                    {t(`table.${c}`)}
                  </th>
                ))}
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((u) => (
                <tr
                  key={u.id}
                  className="bg-background-secondary transition-colors hover:bg-background-tertiary"
                >
                  <td className="px-4 py-3">
                    <span className="font-medium text-foreground">{u.email}</span>
                    {me?.id === u.id && (
                      <span className="ms-2 text-xs text-foreground-muted">{t("you")}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-foreground-muted">{u.full_name}</td>
                  <td className="px-4 py-3">
                    <AccessBadge user={u} />
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={
                        u.is_active
                          ? "inline-flex items-center rounded-full border border-accent/30 px-2 py-0.5 text-xs font-semibold text-accent"
                          : "inline-flex items-center rounded-full border border-border px-2 py-0.5 text-xs font-semibold text-foreground-muted"
                      }
                    >
                      {u.is_active ? t("statusActive") : t("statusInactive")}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-foreground-muted">
                    <time dateTime={u.created_at} title={u.created_at}>
                      {formatTashkent(u.created_at)}
                    </time>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={() => void openEditor(u)}>
                        {t("edit")}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setRowError(null);
                          toggleActive.mutate(u);
                        }}
                        disabled={toggleActive.isPending}
                      >
                        {u.is_active ? t("deactivate") : t("activate")}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing !== undefined && (
        <UserEditor user={editing} onClose={() => setEditing(undefined)} />
      )}
    </>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

function AdminUsersPageContent() {
  const t = useTranslations("admin");
  const router = useRouter();
  const { user, isAdmin, isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated && user && !isAdmin) {
      router.replace("/");
    }
  }, [isAuthenticated, user, isAdmin, router]);

  // `user` null means /auth/me is still in flight — not "not an administrator".
  if (user && !isAdmin) {
    return <RouteGuardFallback />;
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <Users size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("pageTitle")}</h1>
          <p className="mt-0.5 text-sm text-foreground-muted">{t("pageSubtitle")}</p>
        </div>
      </div>
      <UsersTable />
    </div>
  );
}

export default function AdminUsersPage() {
  return (
    <Suspense fallback={<RouteGuardFallback />}>
      <AdminUsersPageContent />
    </Suspense>
  );
}
