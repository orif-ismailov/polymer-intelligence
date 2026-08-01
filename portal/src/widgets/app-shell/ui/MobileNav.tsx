import { useTranslation } from "react-i18next";

import { BottomNav, type BottomNavItem } from "@/shared/ui";

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

  const items: BottomNavItem[] = [
    { to: "/cabinet", label: t("nav.home"), icon: HomeIcon, end: true },
    { to: "/cabinet/requests", label: t("nav.requests"), icon: DocIcon },
    { to: "/cabinet/market", label: t("nav.market"), icon: StoreIcon },
    { to: "/cabinet/deals", label: t("nav.deals"), icon: HandshakeIcon },
    { to: "/cabinet/settings", label: t("nav.settings"), icon: CogIcon },
  ];

  return <BottomNav items={items} />;
}
