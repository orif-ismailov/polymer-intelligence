import { useTranslation } from "react-i18next";

import { BottomNav, type BottomNavItem } from "@/shared/ui";

import { ChatIcon, CogIcon, DocIcon, HomeIcon, StoreIcon } from "./navIcons";

/**
 * The mockups' phone bottom bar, wired to the routes that exist today.
 *
 * Five destinations only — the bar is the primary phone navigation, and the
 * drawer (hamburger) still reaches the full nav. The "Сделки" slot the mockups
 * show lands in P2 with the deals domain; until then this slot is inquiries.
 */
export function MobileNav() {
  const { t } = useTranslation();

  const items: BottomNavItem[] = [
    { to: "/", label: t("nav.home"), icon: HomeIcon, end: true },
    { to: "/requests", label: t("nav.requests"), icon: DocIcon },
    { to: "/market", label: t("nav.market"), icon: StoreIcon },
    { to: "/inquiries", label: t("nav.inquiries"), icon: ChatIcon },
    { to: "/settings", label: t("nav.settings"), icon: CogIcon },
  ];

  return <BottomNav items={items} />;
}
