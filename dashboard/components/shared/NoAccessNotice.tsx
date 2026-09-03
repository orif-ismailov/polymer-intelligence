"use client";

import { ShieldOff } from "lucide-react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/hooks/useAuth";

/**
 * What a staff account with no access to anything sees instead of the dashboard.
 *
 * Authenticating and being authorized are different questions: a valid staff row
 * signs in fine and may still reach nothing. Rendering the shell for them showed
 * all 27 nav items over a grid of `API request failed: 403 Forbidden` — which
 * reads as an outage rather than as a permission boundary, and sends the person
 * to whoever runs the platform to report a bug that isn't one.
 *
 * Says who they are signed in as, because the usual cause is being signed into
 * the wrong account, and offers the one action that helps.
 */
export function NoAccessNotice() {
  const t = useTranslations("noAccess");
  const { user, logout } = useAuth();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <ShieldOff size={32} className="text-foreground-muted" aria-hidden="true" />
      <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
      <p className="max-w-md text-sm text-foreground-muted">{t("body")}</p>
      {user && (
        <p className="text-sm text-foreground-muted">
          {t("signedInAs")} <span className="font-medium text-foreground">{user.email}</span>
        </p>
      )}
      <button
        type="button"
        onClick={() => void logout()}
        className="mt-2 rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-background-tertiary"
      >
        {t("signOut")}
      </button>
    </div>
  );
}
