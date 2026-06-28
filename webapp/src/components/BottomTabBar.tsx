/**
 * Bottom tab bar — the unified navigation from IMG_0046.
 *
 * Маркет · Заявки · Продать · Новости · Профиль. Each tab's active state uses its
 * domain accent (green/blue/orange/purple/text). Fixed to the bottom; AppShell
 * reserves space for it.
 */

import type { CSSProperties } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileText, Newspaper, Plus, Store, User, type LucideIcon } from "lucide-react";

interface Tab {
  key: string;
  path: string;
  color: string;
  Icon: LucideIcon;
}

const TABS: Tab[] = [
  { key: "market", path: "/market", color: "var(--green)", Icon: Store },
  { key: "requests", path: "/requests", color: "var(--blue)", Icon: FileText },
  { key: "sell", path: "/sell", color: "var(--orange)", Icon: Plus },
  { key: "news", path: "/news", color: "var(--purple)", Icon: Newspaper },
  { key: "profile", path: "/profile", color: "var(--text)", Icon: User },
];

export default function BottomTabBar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const bar: CSSProperties = {
    position: "fixed",
    left: 0,
    right: 0,
    bottom: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-around",
    height: "64px",
    paddingBottom: "env(safe-area-inset-bottom)",
    background: "var(--surface)",
    borderTop: "1px solid var(--border)",
    zIndex: 50,
  };

  return (
    <nav style={bar} aria-label="Main">
      {TABS.map(({ key, path, color, Icon }) => {
        const active = pathname === path || pathname.startsWith(`${path}/`);
        const tint = active ? color : "var(--text-muted)";
        return (
          <button
            key={key}
            type="button"
            onClick={() => navigate(path)}
            aria-current={active ? "page" : undefined}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "3px",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              padding: "6px 0",
              color: tint,
            }}
          >
            <Icon size={24} color={tint} />
            <span style={{ fontSize: "11px", fontWeight: 500 }}>{t(`nav.${key}`)}</span>
          </button>
        );
      })}
    </nav>
  );
}
