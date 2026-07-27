import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

import { cn } from "@/shared/lib";

import {
  BuildingIcon,
  ChatIcon,
  CogIcon,
  ContractIcon,
  DocIcon,
  HomeIcon,
  NewsIcon,
  StoreIcon,
  TagIcon,
} from "./navIcons";

interface NavItem {
  to: string;
  labelKey: string;
  icon: ReactNode;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", labelKey: "nav.home", icon: HomeIcon, end: true },
  { to: "/market", labelKey: "nav.market", icon: StoreIcon },
  { to: "/requests", labelKey: "nav.requests", icon: DocIcon },
  { to: "/inquiries", labelKey: "nav.inquiries", icon: ChatIcon },
  { to: "/news", labelKey: "nav.news", icon: NewsIcon },
  { to: "/companies", labelKey: "nav.companies", icon: BuildingIcon },
  { to: "/offers", labelKey: "nav.offers", icon: TagIcon },
  { to: "/contracts", labelKey: "nav.contracts", icon: ContractIcon },
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
