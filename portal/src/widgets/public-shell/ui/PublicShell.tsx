import { useTranslation } from "react-i18next";
import { Link, Outlet } from "react-router-dom";

import { selectIsAuthenticated, useAuthStore } from "@/entities/account";
import { PUBLIC_DIRECTORIES } from "@/shared/config";
import { BrandLogo } from "@/shared/ui";

import { PublicTopNav } from "./PublicTopNav";

/**
 * Chrome for the public storefront: horizontal nav, content, footer.
 *
 * Public, not anonymous — a signed-in visitor reads these pages too, and the
 * only thing their session changes here is the account column and the nav's
 * auth buttons.
 *
 * Wider than the cabinet's `max-w-6xl` because the storefront's body is a
 * three-column layout with a persistent market rail, which does not fit in
 * 1152px without either dropping the rail or squeezing the cards below a
 * readable width.
 */
export function PublicShell() {
  return (
    <div className="flex min-h-[100dvh] flex-col bg-bg text-text">
      <PublicTopNav />
      <main className="flex-1">
        <Outlet />
      </main>
      <PublicFooter />
    </div>
  );
}

function PublicFooter() {
  const { t } = useTranslation();
  const isAuthenticated = useAuthStore(selectIsAuthenticated);

  const columns = [
    {
      titleKey: "public.footer.marketplace",
      links: [
        { to: "/market", labelKey: "public.nav.catalog" },
        { to: "/prices", labelKey: "public.nav.prices" },
        { to: "/news", labelKey: "public.nav.news" },
      ],
    },
    {
      titleKey: "public.footer.directories",
      links: PUBLIC_DIRECTORIES.map((d) => ({
        to: `/${d.slug}`,
        labelKey: d.labelKey,
      })),
    },
    {
      titleKey: "public.footer.account",
      links: isAuthenticated
        ? [{ to: "/cabinet", labelKey: "common.cabinet" }]
        : [
            { to: "/cabinet/login", labelKey: "public.nav.signIn" },
            { to: "/cabinet/login", labelKey: "public.nav.register" },
          ],
    },
  ];

  return (
    <footer className="mt-16 border-t border-border bg-surface">
      <div className="mx-auto max-w-[1440px] px-4 py-10 lg:px-6">
        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-1">
            <Link to="/" aria-label={t("common.appName")} className="inline-flex">
              <BrandLogo withTagline />
            </Link>
            <p className="mt-3 max-w-[32ch] text-sm text-text-muted">
              {t("public.footer.blurb")}
            </p>
          </div>

          {columns.map((col) => (
            <nav key={col.titleKey} aria-label={t(col.titleKey)}>
              <h2 className="text-sm font-semibold text-text">{t(col.titleKey)}</h2>
              <ul className="mt-3 space-y-2">
                {col.links.map((link) => (
                  <li key={`${col.titleKey}-${link.labelKey}`}>
                    <Link
                      to={link.to}
                      className="text-sm text-text-muted transition-colors hover:text-brand"
                    >
                      {t(link.labelKey)}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <p className="mt-10 border-t border-border pt-6 text-xs text-text-subtle">
          {t("public.footer.legal")}
        </p>
      </div>
    </footer>
  );
}
