/**
 * TelegramLoginGate — browser sign-in via the Telegram Login Widget.
 *
 * Only rendered outside the Mini App (browser). It fetches the bot @handle from
 * GET /webapp/auth/config, injects the official Telegram widget script in JS-callback
 * mode (data-onauth), and on success POSTs the signed payload to /webapp/auth/telegram
 * (which sets the httpOnly client_session cookie) before flipping authStore to authed.
 *
 * Callback mode (not redirect mode) is used on purpose: the app routes with HashRouter,
 * and a redirect would append the payload as a query string that fights the hash router.
 *
 * NOTE: the widget only renders/authenticates on a domain registered with BotFather
 * /setdomain. On an unregistered host (e.g. localhost) the button will not appear —
 * that is an ops precondition, not a bug.
 */

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";

import { api } from "../api/client";
import { useAuthStore } from "../store/authStore";
import type { TelegramLoginPayload } from "../types";

declare global {
  interface Window {
    __imexOnTelegramAuth?: (user: TelegramLoginPayload) => void;
  }
}

interface Props {
  onSuccess?: () => void;
}

export default function TelegramLoginGate({ onSuccess }: Props) {
  const { t } = useTranslation();
  const markAuthed = useAuthStore((s) => s.markAuthed);
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Load the bot @handle needed to render the widget.
  useEffect(() => {
    let cancelled = false;
    api
      .getAuthConfig()
      .then((cfg) => {
        if (!cancelled) setBotUsername(cfg.bot_username || "");
      })
      .catch(() => {
        if (!cancelled) setBotUsername("");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Register the global callback + inject the widget script once we know the handle.
  useEffect(() => {
    if (!botUsername || !widgetRef.current) return;
    const container = widgetRef.current;

    window.__imexOnTelegramAuth = (user: TelegramLoginPayload) => {
      setBusy(true);
      setError(null);
      api
        .loginTelegram(user)
        .then(() => {
          markAuthed();
          onSuccess?.();
        })
        .catch(() => setError(t("auth.error")))
        .finally(() => setBusy(false));
    };

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "12");
    script.setAttribute("data-request-access", "write");
    script.setAttribute("data-onauth", "__imexOnTelegramAuth(user)");
    container.appendChild(script);

    return () => {
      container.innerHTML = "";
      delete window.__imexOnTelegramAuth;
    };
  }, [botUsername, markAuthed, onSuccess, t]);

  return (
    <div className="imex-gate">
      <div className="imex-gate__card">
        <span className="imex-gate__logo" aria-hidden="true">
          <Sparkles size={22} />
        </span>
        <h1 className="imex-gate__title">{t("auth.title")}</h1>
        <p className="imex-gate__subtitle">{t("auth.subtitle")}</p>

        {botUsername === null && <p className="imex-gate__muted">{t("auth.loading")}</p>}

        {botUsername === "" && <p className="imex-gate__muted">{t("auth.unavailable")}</p>}

        {botUsername ? <div ref={widgetRef} className="imex-gate__widget" /> : null}

        {busy && <p className="imex-gate__muted">{t("auth.signing")}</p>}
        {error && <p className="imex-gate__error">{error}</p>}
      </div>
    </div>
  );
}
