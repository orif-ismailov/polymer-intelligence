import { BarChart3, Home, LogIn, Newspaper, Store, UserRound } from "lucide-react";
import { useTranslation } from "react-i18next";

import { selectIsAuthenticated, useAuthStore } from "@/entities/account";
import { BottomNav, type BottomNavItem } from "@/shared/ui";

const ICON = { size: 20, strokeWidth: 1.75 } as const;

/**
 * The storefront's phone bottom bar — the cabinet's pattern, on the public side.
 *
 * Same split `AppShell` uses: five primary destinations here, the whole nav
 * still in the header's drawer. Before this, every public destination on a
 * phone was one tap deeper than its cabinet equivalent, and the cabinet's own
 * bar has a «Маркет» item pointing at `/market` — a PUBLIC route, so tapping it
 * dropped the visitor out of the shell that has a bar into one that did not and
 * the navigation vanished underneath them. Now both shells carry it.
 *
 * The five mirror the footer's «Маркетплейс» column plus home and the account.
 * `/market` earns a slot for a second reason: it is absent from the header's
 * `NAV` array entirely, so the catalog had no persistent link anywhere in the
 * chrome. The four company directories stay in the drawer and in the six cards
 * on the home page.
 */
export function PublicMobileNav() {
  const { t } = useTranslation();
  // `token !== null` — false during SSR and at first paint, so the server emits
  // the anonymous «Войти» slot and the swap to «Кабинет» is a state change
  // rather than a hydration mismatch. Same contract the header runs on, and
  // nothing here issues an authenticated request, so the page stays
  // shared-cacheable.
  const isAuthenticated = useAuthStore(selectIsAuthenticated);

  const items: BottomNavItem[] = [
    // `end` only on "/", or every route under it would light this cell up.
    { to: "/", label: t("public.nav.home"), icon: <Home {...ICON} />, end: true },
    // Deliberately NOT `end`: `/market/42` is still the catalog.
    { to: "/market", label: t("public.nav.catalog"), icon: <Store {...ICON} /> },
    // The short label — «Цены и аналитика» is 16 characters in a ~70px cell.
    { to: "/prices", label: t("public.nav.pricesShort"), icon: <BarChart3 {...ICON} /> },
    // Same as the catalog: an article keeps its section lit.
    { to: "/news", label: t("public.nav.news"), icon: <Newspaper {...ICON} /> },
    isAuthenticated
      ? { to: "/cabinet", label: t("common.cabinet"), icon: <UserRound {...ICON} /> }
      : { to: "/cabinet/login", label: t("public.nav.signIn"), icon: <LogIn {...ICON} /> },
  ];

  return <BottomNav items={items} />;
}
