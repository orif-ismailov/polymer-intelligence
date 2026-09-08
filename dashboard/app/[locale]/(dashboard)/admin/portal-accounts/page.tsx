"use client";

/**
 * Cabinet accounts (/admin/portal-accounts)
 *
 * The queue of people asking for access, and the place credentials are issued.
 * Registration (portal `/cabinet/register`) creates a `pending` row and grants
 * nothing; this screen is where somebody decides, and the login+password that
 * comes out is what goes into the contract the two parties sign.
 *
 * Administrator-only, and deliberately not a grantable page: whoever can issue a
 * cabinet credential can sign in as a customer and act inside their company (see
 * backend app/core/pages.py). The redirect below is UX; `require_admin` is the
 * boundary.
 *
 * THE PASSWORD IS SHOWN ONCE. The backend stores an argon2 hash, so no route can
 * return it again — the modal says so, and the only recovery is to regenerate.
 *
 * No hardcoded hex.
 */

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound, UserCog } from "lucide-react";
import { useTranslations } from "next-intl";
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

type AccountStatus = "pending" | "active" | "blocked";

interface PortalAccount {
  id: number;
  status: AccountStatus;
  login: string | null;
  name: string | null;
  phone: string;
  language: string;
  applied_company_name: string | null;
  application_note: string | null;
  must_change_password: boolean;
  credentials_issued_at: string | null;
  credentials_issued_by: number | null;
  last_login_at: string | null;
  created_at: string;
}

interface IssuedCredentials {
  account: PortalAccount;
  login: string;
  password: string;
}

/** Mirrors the backend's `MIN_PASSWORD_LENGTH`; the API rejects anything shorter. */
const MIN_PASSWORD = 12;

/**
 * Turn an API failure into a sentence in the reader's language.
 *
 * The 409s carry `{code, message}`: the code is what we translate, and the English
 * `message` is only a fallback for a code this build has no string for. Rendering
 * `message` directly puts an English sentence on a Russian dashboard — invisible to
 * types and tests, obvious in a browser.
 */
function useApiError() {
  const t = useTranslations("portalAccounts");
  return (e: unknown, fallback: string): string => {
    if (!(e instanceof ApiError)) return fallback;
    const detail = (e.body as { detail?: unknown })?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const { code, message } = detail as { code?: string; message?: string };
      if (code) {
        const key = `errors.${code}`;
        if (t.has(key)) return t(key);
      }
      if (message) return message;
    }
    return fallback;
  };
}

/**
 * Cyrillic → Latin, so a suggested login can be typed on any keyboard.
 *
 * The applicant writes «ООО Полимер Тест» and the obvious suggestion is
 * `ооо-полимер-тест` — a login that is then printed in a contract and typed by hand
 * by someone whose layout may well be Latin. The generated password is already
 * restricted to unambiguous ASCII for exactly this reason; the login has to match it.
 */
const CYRILLIC_TO_LATIN: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i",
  й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t",
  у: "u", ф: "f", х: "h", ц: "ts", ч: "ch", ш: "sh", щ: "sch", ъ: "", ы: "y", ь: "",
  э: "e", ю: "yu", я: "ya", ў: "o", қ: "q", ғ: "g", ҳ: "h",
};

/** A login staff can read out loud, suggested from the applicant's company. */
function suggestLogin(account: PortalAccount): string {
  const base = [...(account.applied_company_name ?? account.name ?? "").toLowerCase()]
    .map((ch) => CYRILLIC_TO_LATIN[ch] ?? ch)
    .join("")
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 24)
    .replace(/-$/, "");
  return base || `client-${account.id}`;
}

// ─── Badges ────────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: AccountStatus }) {
  const t = useTranslations("portalAccounts");
  const tone =
    status === "active"
      ? "border-accent/30 text-accent"
      : status === "pending"
        ? "border-urgency-medium/40 text-urgency-medium"
        : "border-border text-foreground-muted";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${tone}`}
    >
      {t(`status.${status}`)}
    </span>
  );
}

// ─── The one-time credentials modal ────────────────────────────────────────────

function CredentialsDialog({
  issued,
  onClose,
}: {
  issued: IssuedCredentials;
  onClose: () => void;
}) {
  const t = useTranslations("portalAccounts");
  const [copied, setCopied] = useState(false);

  const block = `${t("issued.loginLabel")}: ${issued.login}\n${t("issued.passwordLabel")}: ${issued.password}`;

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("issued.title")}</DialogTitle>
          {/* Said plainly, because it is true and unrecoverable: we keep a hash. */}
          <DialogDescription>{t("issued.onceWarning")}</DialogDescription>
        </DialogHeader>

        <dl className="flex flex-col gap-3 rounded-lg border border-border bg-background-tertiary p-4 font-mono text-sm">
          <div className="flex items-baseline justify-between gap-4">
            <dt className="text-xs uppercase tracking-wider text-foreground-muted">
              {t("issued.loginLabel")}
            </dt>
            <dd className="text-foreground">{issued.login}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-4">
            <dt className="text-xs uppercase tracking-wider text-foreground-muted">
              {t("issued.passwordLabel")}
            </dt>
            <dd className="select-all text-foreground">{issued.password}</dd>
          </div>
        </dl>

        <p className="text-sm text-foreground-muted">{t("issued.contractHint")}</p>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => {
              void navigator.clipboard.writeText(block).then(() => setCopied(true));
            }}
          >
            {copied ? (
              <Check className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Copy className="h-4 w-4" aria-hidden="true" />
            )}
            {copied ? t("issued.copied") : t("issued.copy")}
          </Button>
          <Button onClick={onClose}>{t("issued.done")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Issue / regenerate ────────────────────────────────────────────────────────

function IssueDialog({
  account,
  onIssued,
  onClose,
}: {
  account: PortalAccount;
  onIssued: (issued: IssuedCredentials) => void;
  onClose: () => void;
}) {
  const t = useTranslations("portalAccounts");
  const apiError = useApiError();
  const qc = useQueryClient();
  const regenerating = account.login !== null;

  const [login, setLogin] = useState(account.login ?? suggestLogin(account));
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      apiFetch<IssuedCredentials>(
        regenerating
          ? `/admin/portal-accounts/${account.id}/password`
          : `/admin/portal-accounts/${account.id}/credentials`,
        {
          method: "POST",
          body: JSON.stringify(
            regenerating
              ? { password: password || null }
              : { login: login.trim(), password: password || null },
          ),
        },
      ),
    onSuccess: (issued) => {
      void qc.invalidateQueries({ queryKey: ["portal-accounts"] });
      onIssued(issued);
    },
    onError: (e: unknown) => setError(apiError(e, t("saveError"))),
  });

  const passwordOk = password === "" || password.length >= MIN_PASSWORD;
  const canSave = (regenerating || login.trim().length > 0) && passwordOk && !save.isPending;

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{regenerating ? t("regenerate.title") : t("issue.title")}</DialogTitle>
          <DialogDescription>
            {regenerating ? t("regenerate.subtitle") : t("issue.subtitle")}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {!regenerating && (
            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-foreground">{t("issue.login")}</span>
              <Input
                value={login}
                onChange={(e) => setLogin(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
              <span className="text-xs text-foreground-muted">{t("issue.loginHint")}</span>
            </label>
          )}

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-foreground">{t("issue.password")}</span>
            <Input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("issue.passwordPlaceholder")}
              autoComplete="off"
              spellCheck={false}
            />
            <span className="text-xs text-foreground-muted">
              {password === "" ? t("issue.generateHint") : t("issue.minLength", { n: MIN_PASSWORD })}
            </span>
          </label>

          {error && (
            <div className="rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-3 text-sm text-urgency-high">
              {error}
            </div>
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
            {save.isPending ? t("saving") : t("issue.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Table ─────────────────────────────────────────────────────────────────────

const FILTERS = ["pending", "active", "blocked", "all"] as const;

function AccountsTable() {
  const t = useTranslations("portalAccounts");
  const apiError = useApiError();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("pending");
  const [issuing, setIssuing] = useState<PortalAccount | null>(null);
  const [issued, setIssued] = useState<IssuedCredentials | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const { data: accounts = [], isLoading, error } = useQuery<PortalAccount[]>({
    queryKey: ["portal-accounts", filter],
    queryFn: () =>
      apiFetch<PortalAccount[]>(
        `/admin/portal-accounts${filter === "all" ? "" : `?status=${filter}`}`,
      ),
  });

  const toggleBlocked = useMutation({
    mutationFn: (a: PortalAccount) =>
      apiFetch<PortalAccount>(
        `/admin/portal-accounts/${a.id}/${a.status === "blocked" ? "unblock" : "block"}`,
        { method: "POST" },
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["portal-accounts"] }),
    onError: (e: unknown) => setRowError(apiError(e, t("saveError"))),
  });

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
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1.5">
          {FILTERS.map((f) => (
            <Button
              key={f}
              variant={filter === f ? "default" : "ghost"}
              size="sm"
              onClick={() => setFilter(f)}
            >
              {t(`filter.${f}`)}
            </Button>
          ))}
        </div>
        <p className="text-sm text-foreground-muted">
          {t("countLabel", { count: accounts.length })}
        </p>
      </div>

      {rowError && (
        <div className="mb-3 rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-3 text-sm text-urgency-high">
          {rowError}
        </div>
      )}

      {accounts.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <UserCog size={32} className="text-foreground-muted" aria-hidden="true" />
          <p className="text-sm text-foreground-muted">{t("empty")}</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-tertiary">
              <tr>
                {["applicant", "company", "login", "status", "createdAt"].map((c) => (
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
              {accounts.map((a) => (
                <tr
                  key={a.id}
                  className="bg-background-secondary transition-colors hover:bg-background-tertiary"
                >
                  <td className="px-4 py-3">
                    <span className="font-medium text-foreground">{a.name ?? "—"}</span>
                    <span className="block text-xs text-foreground-muted">{a.phone}</span>
                  </td>
                  <td className="px-4 py-3 text-foreground-muted">
                    {a.applied_company_name ?? "—"}
                    {a.application_note && (
                      <span
                        className="block truncate text-xs italic"
                        title={a.application_note}
                      >
                        {a.application_note}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-foreground-muted">
                    {a.login ?? "—"}
                    {a.must_change_password && a.login && (
                      <span className="block text-xs not-italic">{t("mustChange")}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={a.status} />
                  </td>
                  <td className="px-4 py-3 text-foreground-muted">
                    <time dateTime={a.created_at} title={a.created_at}>
                      {formatTashkent(a.created_at)}
                    </time>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setIssuing(a)}>
                        <KeyRound className="h-4 w-4" aria-hidden="true" />
                        {a.login ? t("regenerate.action") : t("issue.action")}
                      </Button>
                      {a.login && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setRowError(null);
                            toggleBlocked.mutate(a);
                          }}
                          disabled={toggleBlocked.isPending}
                        >
                          {a.status === "blocked" ? t("unblock") : t("block")}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {issuing && (
        <IssueDialog
          account={issuing}
          onIssued={(result) => {
            setIssuing(null);
            setIssued(result);
          }}
          onClose={() => setIssuing(null)}
        />
      )}
      {issued && <CredentialsDialog issued={issued} onClose={() => setIssued(null)} />}
    </>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

function PortalAccountsPageContent() {
  const t = useTranslations("portalAccounts");
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
        <UserCog size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("pageTitle")}</h1>
          <p className="mt-0.5 text-sm text-foreground-muted">{t("pageSubtitle")}</p>
        </div>
      </div>
      <AccountsTable />
    </div>
  );
}

export default function PortalAccountsPage() {
  return (
    <Suspense fallback={<RouteGuardFallback />}>
      <PortalAccountsPageContent />
    </Suspense>
  );
}
