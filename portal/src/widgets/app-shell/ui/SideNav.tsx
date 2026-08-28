import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";
import { Link, NavLink } from "react-router-dom";

import { companyHasFeature, useActiveCompany, type FeatureKey } from "@/entities/company";
import { cn } from "@/shared/lib";

import { requestsNavLabelKey } from "../model/requestsNavLabel";

import {
  BuildingIcon,
  ChatIcon,
  CogIcon,
  ContractIcon,
  DocIcon,
  FlaskNavIcon,
  GavelIcon,
  TruckNavIcon,
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
  /**
   * Shown only when the active company's account type has this feature
   * (`entities/company/model/features.ts`). No key = universal entry.
   */
  feature?: FeatureKey;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/cabinet", labelKey: "nav.home", icon: HomeIcon, end: true },
  { to: "/market", labelKey: "nav.market", icon: StoreIcon },
  { to: "/manufacturers", labelKey: "nav.manufacturers", icon: ManufacturersIcon },
  { to: "/cabinet/market/favorites", labelKey: "nav.favorites", icon: HeartIcon, feature: "favorites" },
  // This slot is universal on purpose: the buyer's tenders, or the broadcast
  // pool for a carrier/lab — RequestsRouteSwitch picks the page, and
  // `requestsNavLabelKey` names it for whoever is looking.
  { to: "/cabinet/requests", labelKey: "nav.requests", icon: DocIcon },
  // The other end of the same object: tenders OTHER companies announced, which
  // a supplier quotes against. It had a route and a role gate but no way in —
  // reachable only from a notification or the deals page.
  { to: "/cabinet/market/requests", labelKey: "nav.openTenders", icon: GavelIcon, feature: "rfqInbox" },
  { to: "/cabinet/deals", labelKey: "nav.deals", icon: HandshakeIcon },
  { to: "/cabinet/inquiries", labelKey: "nav.inquiries", icon: ChatIcon, feature: "inquiries" },
  { to: "/cabinet/samples", labelKey: "nav.samples", icon: SampleBoxIcon, feature: "samples" },
  {
    to: "/cabinet/lab",
    labelKey: "nav.lab",
    icon: FlaskNavIcon,
    // The lab hub: marketplace analysis requests + partner-lab orders in one
    // page. Gated on the wider `labOrdering`; the page itself decides whether
    // the orders tab exists. A laboratory reads the broadcast pool at «Заявки»
    // instead, so this would only ever be an empty page for one.
    feature: "labOrdering",
  },
  {
    to: "/cabinet/logistics/requests",
    labelKey: "nav.logisticsRequests",
    icon: TruckNavIcon,
    // The buyer's own logistics requests. A carrier reads the broadcast pool at
    // «Заявки» instead, so this entry would only ever be an empty page for one.
    feature: "logisticsOrdering",
  },
  // Out to the public reader — news has no cabinet twin any more.
  { to: "/news", labelKey: "nav.news", icon: NewsIcon },
  { to: "/cabinet/companies", labelKey: "nav.companies", icon: BuildingIcon },
  { to: "/cabinet/offers", labelKey: "nav.offers", icon: TagIcon, feature: "offers" },
  { to: "/cabinet/contracts", labelKey: "nav.contracts", icon: ContractIcon },
  { to: "/cabinet/settings", labelKey: "nav.settings", icon: CogIcon },
];

interface SideNavProps {
  onNavigate?: () => void;
}

export function SideNav({ onNavigate }: SideNavProps) {
  const { t } = useTranslation();
  // The menu is shaped by the active company's account type: a laboratory has
  // no «Предложения», a buyer no reason to see a supplier inbox. The same
  // matrix drives the route guards, so a hidden entry is also an unreachable
  // page — hiding here is presentation, not the enforcement.
  const { activeCompany } = useActiveCompany();
  const requestsLabelKey = requestsNavLabelKey(activeCompany);
  const items = NAV_ITEMS.filter(
    (item) => !item.feature || companyHasFeature(activeCompany, item.feature),
  );
  return (
    <nav className="flex flex-col gap-1" aria-label={t("common.cabinet")}>
      {items.map((item) => (
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
          {t(item.to === "/cabinet/requests" ? requestsLabelKey : item.labelKey)}
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
