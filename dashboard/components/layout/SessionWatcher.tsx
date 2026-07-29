"use client";

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/hooks/useAuth";
import { onSessionChange, type SessionEvent } from "@/lib/session";

/**
 * Warns when the browser's session identity changed in another tab.
 *
 * The refresh cookie is shared across tabs, so a colleague signing in on the same
 * browser silently re-points every other open tab at their account on the next
 * navigation — a staff member could go on working in what looks like their own
 * dashboard while acting as someone else. Tab-scoped sessions are not worth the
 * complexity for an internal tool, but silence is: this makes the takeover
 * explicit and blocks the stale tab until it is reloaded under the new identity.
 */
export function SessionWatcher() {
  const t = useTranslations("nav.sessionChanged");
  const { user } = useAuth();
  const [event, setEvent] = useState<SessionEvent | null>(null);

  const currentUserId = user?.id ?? null;

  useEffect(() => {
    return onSessionChange((next) => {
      // A different account signed in here, or the session was ended elsewhere.
      // The same user signing in again is not a takeover — stay quiet.
      if (next.type === "signin" && next.userId === currentUserId) return;
      setEvent(next);
    });
  }, [currentUserId]);

  if (!event) return null;

  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="session-changed-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-background-secondary p-5 shadow-lg">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-400" aria-hidden="true" />
          <div className="min-w-0">
            <h2 id="session-changed-title" className="text-sm font-semibold text-foreground">
              {t("title")}
            </h2>
            <p className="mt-1 text-sm text-foreground-muted">
              {event.type === "signout" ? t("signedOut") : t("switched")}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-4 w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-dark focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background-secondary"
        >
          {t("reload")}
        </button>
      </div>
    </div>
  );
}
