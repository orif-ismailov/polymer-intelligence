/**
 * RequireAuth — gate for the functional (non-landing) routes.
 *
 * Mini App: always authed → renders children. Browser: renders the Telegram login
 * gate until the visitor signs in (authStore flips to 'authed', which re-renders us).
 * While auth is resolving at boot we show a spinner to avoid a gate flash.
 */

import type { ReactNode } from "react";

import { useAuthStore } from "../store/authStore";
import TelegramLoginGate from "./TelegramLoginGate";

function Spinner() {
  return (
    <div
      style={{
        minHeight: "60vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          width: "32px",
          height: "32px",
          borderRadius: "50%",
          border: "3px solid var(--border)",
          borderTopColor: "var(--green)",
          animation: "spin 0.8s linear infinite",
        }}
      />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export default function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuthStore((s) => s.status);

  if (status === "loading") return <Spinner />;
  if (status === "anon") return <TelegramLoginGate />;
  return <>{children}</>;
}
