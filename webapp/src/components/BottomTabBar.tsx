/**
 * Bottom tab bar — flat 5-tab navigation per docs/design_2.jpeg.
 *
 * Главная · Заявки · Маркет · Новости · Профиль. No center FAB: selling is reached
 * from the Home screen's "Продать сырьё" CTA (→ the Продать hub). Заявки carries a
 * live count badge; each tab's active state uses its domain accent (design-system §4).
 */

import { useEffect, useState, type CSSProperties } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileText, Home, Newspaper, Store, User, type LucideIcon } from "lucide-react";

import { api } from "../api/client";

interface Tab {
  key: string;
  path: string;
  color: string;
  Icon: LucideIcon;
}

const TABS: Tab[] = [
  { key: "home", path: "/", color: "var(--green)", Icon: Home },
  { key: "requests", path: "/requests", color: "var(--blue)", Icon: FileText },
  { key: "market", path: "/market", color: "var(--green)", Icon: Store },
  { key: "news", path: "/news", color: "var(--purple)", Icon: Newspaper },
  { key: "profile", path: "/profile", color: "var(--text)", Icon: User },
];

export default function BottomTabBar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [requestCount, setRequestCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .getRequests()
      .then((r) => {
        if (!cancelled) setRequestCount(r.length);
      })
      .catch(() => {
        /* badge is best-effort */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const bar: CSSProperties = {
    position: "fixed",
    left: 0,
    right: 0,
    bottom: 0,
    display: "flex",
    alignItems: "stretch",
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
        const active = path === "/" ? pathname === "/" : pathname === path || pathname.startsWith(`${path}/`);
        const tint = active ? color : "var(--text-muted)";
        const showBadge = key === "requests" && requestCount > 0;

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
              justifyContent: "center",
              gap: "4px",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              padding: "8px 0",
              color: tint,
            }}
          >
            <span style={{ position: "relative" }}>
              <Icon size={24} color={tint} />
              {showBadge && (
                <span
                  style={{
                    position: "absolute",
                    top: "-6px",
                    right: "-10px",
                    minWidth: "16px",
                    height: "16px",
                    padding: "0 4px",
                    borderRadius: "var(--r-full)",
                    background: "var(--green)",
                    color: "var(--green-on)",
                    fontSize: "10px",
                    fontWeight: 700,
                    lineHeight: "16px",
                    textAlign: "center",
                  }}
                >
                  {requestCount}
                </span>
              )}
            </span>
            <span style={{ fontSize: "11px", fontWeight: 500 }}>{t(`nav.${key}`)}</span>
          </button>
        );
      })}
    </nav>
  );
}
