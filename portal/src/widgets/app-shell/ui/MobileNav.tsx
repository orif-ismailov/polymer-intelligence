import { useTranslation } from "react-i18next";

import { useActiveCompany } from "@/entities/company";
import { BottomNav, type BottomNavItem } from "@/shared/ui";

import { requestsNavLabelKey } from "../model/requestsNavLabel";
import { CogIcon, DocIcon, HandshakeIcon, HomeIcon, StoreIcon } from "./navIcons";

/**
 * The mockups' phone bottom bar, wired to the routes that exist today.
 *
 * Five destinations only — the bar is the primary phone navigation, and the
 * drawer (hamburger) still reaches the full nav. The mockups' "Сделки" slot now
 * holds the deals domain (P2); inquiries stay reachable from the drawer.
 */
export function MobileNav() {
  const { t } = useTranslation();
  const { activeCompany } = useActiveCompany();

  const items: BottomNavItem[] = [
    { to: "/cabinet", label: t("nav.home"), icon: HomeIcon, end: true },
    { to: "/cabinet/requests", label: t(requestsNavLabelKey(activeCompany)), icon: DocIcon },
    { to: "/market", label: t("nav.market"), icon: StoreIcon },
    { to: "/cabinet/deals", label: t("nav.deals"), icon: HandshakeIcon },
    { to: "/cabinet/settings", label: t("nav.settings"), icon: CogIcon },
  ];

  return <BottomNav items={items} />;
}
