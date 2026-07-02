/**
 * TopNav — desktop navigation for the functional (in-app) routes.
 *
 * Replaces the mobile bottom tab bar / compact header on wide viewports (see
 * useIsDesktop). Rendered by AppLayout only on desktop + when authenticated. Uses the
 * app design tokens (NOT the landing palette) so it matches the inner screens.
 */

import type { CSSProperties } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileText, Home, LogOut, Newspaper, Settings, Sparkles, Store } from "lucide-react";

import { useAuthStore } from "../store/authStore";
import LanguageSwitcher from "./LanguageSwitcher";

const LINKS = [
  { key: "market", path: "/market", Icon: Store },
  { key: "requests", path: "/requests", Icon: FileText },
  { key: "sell", path: "/sell", Icon: Store },
  { key: "news", path: "/news", Icon: Newspaper },
  { key: "profile", path: "/profile", Icon: Settings },
] as const;

export default function TopNav() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isMiniApp = useAuthStore((s) => s.isMiniApp);
  const logout = useAuthStore((s) => s.logout);

  const bar: CSSProperties = {
    position: "sticky",
    top: 0,
    zIndex: 40,
    display: "flex",
    alignItems: "center",
    gap: "24px",
    height: "64px",
    padding: "0 24px",
    background: "color-mix(in srgb, var(--bg) 82%, transparent)",
    backdropFilter: "blur(10px)",
    borderBottom: "1px solid var(--border)",
  };

  return (
    <header style={bar}>
      <button
        type="button"
        onClick={() => navigate("/")}
        aria-label="IMEX AI"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "10px",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          padding: 0,
        }}
      >
        <span
          style={{
            width: "30px",
            height: "30px",
            borderRadius: "var(--r-sm)",
            background: "var(--green)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Sparkles size={17} color="var(--green-on)" />
        </span>
        <span style={{ fontSize: "17px", fontWeight: 800, color: "var(--text)", letterSpacing: "-0.01em" }}>
          IMEX <span style={{ color: "var(--green)" }}>AI</span>
        </span>
      </button>

      <nav style={{ display: "flex", alignItems: "center", gap: "4px", marginLeft: "8px" }} aria-label="Main">
        <NavItem
          label={t("nav.home")}
          Icon={Home}
          active={pathname === "/market" ? false : pathname === "/"}
          onClick={() => navigate("/")}
        />
        {LINKS.map(({ key, path, Icon }) => (
          <NavItem
            key={key}
            label={t(`nav.${key}`)}
            Icon={Icon}
            active={pathname === path || pathname.startsWith(`${path}/`)}
            onClick={() => navigate(path)}
          />
        ))}
      </nav>

      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "12px" }}>
        <LanguageSwitcher />
        {!isMiniApp && (
          <button
            type="button"
            onClick={() => void logout()}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              minHeight: "36px",
              padding: "6px 12px",
              borderRadius: "var(--r-full)",
              border: "1px solid var(--border)",
              background: "var(--surface)",
              color: "var(--text-muted)",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <LogOut size={15} /> {t("auth.logout")}
          </button>
        )}
      </div>
    </header>
  );
}

function NavItem({
  label,
  Icon,
  active,
  onClick,
}: {
  label: string;
  Icon: typeof Home;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "7px",
        padding: "8px 14px",
        borderRadius: "var(--r-full)",
        border: "none",
        background: active ? "var(--surface-2)" : "transparent",
        color: active ? "var(--text)" : "var(--text-muted)",
        fontSize: "14px",
        fontWeight: active ? 600 : 500,
        cursor: "pointer",
      }}
    >
      <Icon size={17} color={active ? "var(--green)" : "var(--text-muted)"} />
      {label}
    </button>
  );
}
