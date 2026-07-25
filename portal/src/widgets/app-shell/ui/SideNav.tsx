import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

import { cn } from "@/shared/lib";

interface NavItem {
  to: string;
  labelKey: string;
  icon: ReactNode;
  end?: boolean;
}

const HomeIcon = (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 9l7-6 7 6v8a1 1 0 0 1-1 1h-4v-5H8v5H4a1 1 0 0 1-1-1V9z" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);
const BuildingIcon = (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M4 17V4a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v13M13 8h2a1 1 0 0 1 1 1v8M3 17h14M7 6h2M7 9h2M7 12h2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);
const TagIcon = (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 8.5V4a1 1 0 0 1 1-1h4.5L17 11.5 11.5 17 3 8.5z" stroke="currentColor" strokeWidth="1.4" />
    <circle cx="7" cy="7" r="1.2" fill="currentColor" />
  </svg>
);
const CogIcon = (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.4" />
    <path d="M10 3v2M10 15v2M3 10h2M15 10h2M5 5l1.4 1.4M13.6 13.6L15 15M15 5l-1.4 1.4M6.4 13.6L5 15" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);
const StoreIcon = (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 8V6l1-3h12l1 3v2M3 8h14v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8zM3 8a2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
  </svg>
);
const ChatIcon = (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M4 4h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H8l-4 3v-3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
  </svg>
);
const DocIcon = (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M5 3h6l4 4v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM11 3v4h4M7 11h6M7 14h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const NAV_ITEMS: NavItem[] = [
  { to: "/", labelKey: "nav.home", icon: HomeIcon, end: true },
  { to: "/market", labelKey: "nav.market", icon: StoreIcon },
  { to: "/requests", labelKey: "nav.requests", icon: DocIcon },
  { to: "/inquiries", labelKey: "nav.inquiries", icon: ChatIcon },
  { to: "/companies", labelKey: "nav.companies", icon: BuildingIcon },
  { to: "/offers", labelKey: "nav.offers", icon: TagIcon },
  { to: "/settings", labelKey: "nav.settings", icon: CogIcon },
];

interface SideNavProps {
  onNavigate?: () => void;
}

export function SideNav({ onNavigate }: SideNavProps) {
  const { t } = useTranslation();
  return (
    <nav className="flex flex-col gap-1" aria-label={t("common.cabinet")}>
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-brand-soft text-brand"
                : "text-text-muted hover:bg-surface-2 hover:text-text",
            )
          }
        >
          {item.icon}
          {t(item.labelKey)}
        </NavLink>
      ))}
    </nav>
  );
}
