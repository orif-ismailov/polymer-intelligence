import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

import { companyHasFeature, useActiveCompany, type FeatureKey } from "@/entities/company";
import { cn } from "@/shared/lib";
import { Tooltip } from "@/shared/ui";

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
  SampleBoxIcon,
  StoreIcon,
  TagIcon,
} from "./navIcons";

/**
 * The sections the nav is cut into.
 *
 * Fifteen destinations in one flat run is a wall to read and a wall to scan;
 * grouped, the eye lands on the four or five that matter for what it is doing.
 * `null` is the ungrouped head of the list — «Главная» belongs to no section
 * because it *is* the section everything else hangs off.
 */
type NavGroup = "market" | "trade" | "services" | "company";

const GROUP_ORDER: NavGroup[] = ["market", "trade", "services", "company"];

interface NavItem {
  to: string;
  labelKey: string;
  icon: ReactNode;
  end?: boolean;
  /** Which section this entry sits under; omitted = the ungrouped head. */
  group?: NavGroup;
  /**
   * Shown only when the active company's account type has this feature
   * (`entities/company/model/features.ts`). No key = universal entry.
   */
  feature?: FeatureKey;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/cabinet", labelKey: "nav.home", icon: HomeIcon, end: true },

  { to: "/market", labelKey: "nav.market", icon: StoreIcon, group: "market" },
  {
    to: "/manufacturers",
    labelKey: "nav.manufacturers",
    icon: ManufacturersIcon,
    group: "market",
  },
  {
    to: "/cabinet/market/favorites",
    labelKey: "nav.favorites",
    icon: HeartIcon,
    group: "market",
    feature: "favorites",
  },

  // This slot is universal on purpose: the buyer's tenders, or the broadcast
  // pool for a carrier/lab — RequestsRouteSwitch picks the page, and
  // `requestsNavLabelKey` names it for whoever is looking.
  { to: "/cabinet/requests", labelKey: "nav.requests", icon: DocIcon, group: "trade" },
  // The other end of the same object: tenders OTHER companies announced, which
  // a supplier quotes against. It had a route and a role gate but no way in —
  // reachable only from a notification or the deals page.
  {
    to: "/cabinet/market/requests",
    labelKey: "nav.openTenders",
    icon: GavelIcon,
    group: "trade",
    feature: "rfqInbox",
  },
  { to: "/cabinet/deals", labelKey: "nav.deals", icon: HandshakeIcon, group: "trade" },
  {
    to: "/cabinet/inquiries",
    labelKey: "nav.inquiries",
    icon: ChatIcon,
    group: "trade",
    feature: "inquiries",
  },
  { to: "/cabinet/contracts", labelKey: "nav.contracts", icon: ContractIcon, group: "trade" },

  {
    to: "/cabinet/samples",
    labelKey: "nav.samples",
    icon: SampleBoxIcon,
    group: "services",
    feature: "samples",
  },
  {
    to: "/cabinet/lab",
    labelKey: "nav.lab",
    icon: FlaskNavIcon,
    group: "services",
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
    group: "services",
    // The buyer's own logistics requests. A carrier reads the broadcast pool at
    // «Заявки» instead, so this entry would only ever be an empty page for one.
    feature: "logisticsOrdering",
  },
  // Out to the public reader — news has no cabinet twin any more.
  { to: "/news", labelKey: "nav.news", icon: NewsIcon, group: "services" },

  { to: "/cabinet/companies", labelKey: "nav.companies", icon: BuildingIcon, group: "company" },
  {
    to: "/cabinet/offers",
    labelKey: "nav.offers",
    icon: TagIcon,
    group: "company",
    feature: "offers",
  },
  { to: "/cabinet/settings", labelKey: "nav.settings", icon: CogIcon, group: "company" },
];

interface SideNavProps {
  onNavigate?: () => void;
  /**
   * Icon-only rail. Labels move into tooltips and `aria-label`, so the links
   * keep their accessible names — an icon-only control with no name is the
   * failure this mode invites.
   */
  collapsed?: boolean;
  /**
   * The phone drawer wants full 44px rows; the desktop rail is a pointer
   * surface and reads better at 40.
   */
  touch?: boolean;
}

export function SideNav({ onNavigate, collapsed = false, touch = false }: SideNavProps) {
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

  const labelOf = (item: NavItem): string =>
    t(item.to === "/cabinet/requests" ? requestsLabelKey : item.labelKey);

  const renderItem = (item: NavItem) => {
    const label = labelOf(item);
    const link = (
      <NavLink
        to={item.to}
        end={item.end}
        onClick={onNavigate}
        aria-label={collapsed ? label : undefined}
        className={({ isActive }) =>
          cn(
            "flex items-center rounded-md text-sm font-medium transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            // Collapsed rows span the rail: a 36px-wide target centred in a
            // 64px column is under the 44px minimum and wastes the easiest
            // pixels to hit.
            collapsed ? "w-full justify-center px-2 py-2.5" : "gap-3 px-3",
            !collapsed && (touch ? "py-3" : "py-2.5"),
            isActive
              ? "bg-brand-soft text-brand"
              : "text-text-muted hover:bg-surface-2 hover:text-text",
          )
        }
      >
        {item.icon}
        {collapsed ? null : label}
      </NavLink>
    );

    if (!collapsed) return <li key={item.to}>{link}</li>;
    return (
      <li key={item.to}>
        <Tooltip content={label} placement="right" className="w-full">
          {link}
        </Tooltip>
      </li>
    );
  };

  const ungrouped = items.filter((item) => !item.group);

  return (
    <nav className="flex flex-col gap-1" aria-label={t("common.cabinet")}>
      <ul className="flex flex-col gap-1">{ungrouped.map(renderItem)}</ul>

      {GROUP_ORDER.map((group) => {
        const groupItems = items.filter((item) => item.group === group);
        // A supplier has no «Образцы» and a laboratory no «Предложения» — a
        // heading over an empty list is worse than no heading.
        if (groupItems.length === 0) return null;
        const title = t(`nav.groups.${group}`);
        return (
          /*
           * `role="group"` + `aria-label`, deliberately NOT a <section> with an
           * <h2>. The rail renders before <main> in the DOM, so a heading here
           * puts an h2 ahead of the page's own h1 and breaks the document
           * outline for everyone navigating by heading — and axe runs on
           * cabinet pages. The label is announced once, as the group's name;
           * the visible copy of it is decorative.
           */
          <div key={group} role="group" aria-label={title}>
            {collapsed ? (
              // The word cannot fit at 64px, so the grouping survives as a
              // rule. `aria-label` above carries it for a screen reader.
              <hr className="mx-2 my-2 border-t border-border" />
            ) : (
              <div
                aria-hidden="true"
                className="px-3 pb-1 pt-4 text-xs font-medium uppercase tracking-wide text-text-subtle"
              >
                {title}
              </div>
            )}
            <ul className="flex flex-col gap-1">{groupItems.map(renderItem)}</ul>
          </div>
        );
      })}

      {/*
       * There is no «Маркетплейс» entry here any more.
       *
       * It pointed at `/` — the storefront home — which is exactly where the
       * `BrandLogo` in the topbar goes, from every surface that draws it,
       * phones included. Two controls, one destination, sitting a few hundred
       * pixels apart; `public-authed.spec.ts` even called them "the two ways
       * back out". The lockup is the one that generalises (it is on the login
       * and onboarding screens too, which have no rail at all), so it is the
       * one that stays.
       *
       * Note it was never a duplicate of «Рынок» above: that is `/market`, the
       * offer catalogue, and it keeps its place.
       */}
    </nav>
  );
}
