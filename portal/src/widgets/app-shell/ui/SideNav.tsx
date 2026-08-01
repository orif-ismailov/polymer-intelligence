import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";
import { Link, NavLink } from "react-router-dom";

import { cn } from "@/shared/lib";

import {
  BuildingIcon,
  ChatIcon,
  CogIcon,
  ContractIcon,
  DocIcon,
  FlaskNavIcon,
  HandshakeIcon,
  HeartIcon,
  HomeIcon,
  ManufacturersIcon,
  NewsIcon,
  PublicSiteIcon,
  SampleBoxIcon,
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
  { to: "/cabinet", labelKey: "nav.home", icon: HomeIcon, end: true },
  { to: "/cabinet/market", labelKey: "nav.market", icon: StoreIcon },
  { to: "/cabinet/manufacturers", labelKey: "nav.manufacturers", icon: ManufacturersIcon },
  { to: "/cabinet/market/favorites", labelKey: "nav.favorites", icon: HeartIcon },
  { to: "/cabinet/requests", labelKey: "nav.requests", icon: DocIcon },
  { to: "/cabinet/deals", labelKey: "nav.deals", icon: HandshakeIcon },
  { to: "/cabinet/inquiries", labelKey: "nav.inquiries", icon: ChatIcon },
  { to: "/cabinet/samples", labelKey: "nav.samples", icon: SampleBoxIcon },
  { to: "/cabinet/lab-orders", labelKey: "nav.labOrders", icon: FlaskNavIcon },
  { to: "/cabinet/news", labelKey: "nav.news", icon: NewsIcon },
  { to: "/cabinet/companies", labelKey: "nav.companies", icon: BuildingIcon },
  { to: "/cabinet/offers", labelKey: "nav.offers", icon: TagIcon },
  { to: "/cabinet/contracts", labelKey: "nav.contracts", icon: ContractIcon },
  { to: "/cabinet/settings", labelKey: "nav.settings", icon: CogIcon },
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

      {/*
       * Out of the cabinet and onto the public storefront. A plain `Link`, not a
       * `NavLink`: `/` is never the active route from in here, and `end` would
       * only make that explicit rather than useful.
       *
       * It sits below the rule because it leaves the namespace every item above
       * it stays inside — and because on phones this drawer is the only place it
       * fits; the bottom bar's five slots are all primary destinations.
       */}
      <Link
        to="/"
        onClick={onNavigate}
        className="mt-2 flex items-center gap-3 border-t border-border px-3 pb-2 pt-4 text-sm font-medium text-text-muted transition-colors hover:text-text"
      >
        {PublicSiteIcon}
        {t("nav.marketplace")}
      </Link>
    </nav>
  );
}
