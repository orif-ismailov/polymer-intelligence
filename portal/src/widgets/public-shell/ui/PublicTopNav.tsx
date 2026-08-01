import { useState } from "react";

import { ChevronDown, Globe, Menu, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, NavLink } from "react-router-dom";

import { selectIsAuthenticated, useAuthStore } from "@/entities/account";
import { PUBLIC_DIRECTORIES } from "@/shared/config";
import { SUPPORTED_LANGS, setLanguage, type Lang } from "@/shared/i18n";
import { cn } from "@/shared/lib";
import { BrandLogo, Button, LinkButton } from "@/shared/ui";

interface NavEntry {
  to: string;
  labelKey: string;
  end?: boolean;
}

/**
 * Storefront primary nav — locked to `docs/new-design/marketplace.jpeg` §1:
 * oversized logo · links left-aligned beside it | bare language control ·
 * neutral-outlined Войти · solid Регистрация, flush with the container edge.
 *
 * Measured off the mockup (source px, ×1.201 for the 1440 layout): bar 64 tall,
 * links start 55px after the lockup and sit 22px apart, the language control has
 * no pill, and there is **no bottom hairline** — the hero card's own border does
 * that separation.
 */
const NAV: NavEntry[] = [
  { to: "/", labelKey: "public.nav.home", end: true },
  ...PUBLIC_DIRECTORIES.map((d) => ({ to: `/${d.slug}`, labelKey: d.labelKey })),
  { to: "/prices", labelKey: "public.nav.prices" },
  { to: "/news", labelKey: "public.nav.news" },
];

const LANG_LABELS: Record<Lang, string> = { ru: "RU", uz: "UZ", en: "EN" };

function LanguageMenu() {
  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const current = (SUPPORTED_LANGS as readonly string[]).includes(i18n.language)
    ? (i18n.language as Lang)
    : "ru";

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="inline-flex h-9 items-center gap-1.5 rounded-md px-2 text-sm font-medium text-text transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <Globe size={15} strokeWidth={1.75} aria-hidden />
        {LANG_LABELS[current]}
        <ChevronDown size={14} strokeWidth={1.75} aria-hidden className="text-text-muted" />
      </button>
      {open ? (
        <>
          <button
            type="button"
            aria-hidden
            tabIndex={-1}
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setOpen(false)}
          />
          <ul
            role="menu"
            className="absolute end-0 z-20 mt-1 min-w-[7rem] overflow-hidden rounded-md border border-border bg-surface py-1 shadow-lg animate-fade-in"
          >
            {SUPPORTED_LANGS.map((lang) => (
              <li key={lang}>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setLanguage(lang);
                    setOpen(false);
                  }}
                  className={cn(
                    "flex w-full items-center px-3 py-1.5 text-sm transition-colors",
                    lang === current
                      ? "bg-brand-soft text-brand"
                      : "text-text-muted hover:bg-surface-2 hover:text-text",
                  )}
                >
                  {LANG_LABELS[lang]}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

export function PublicTopNav() {
  const { t } = useTranslation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Deliberately the whole of the session on the storefront: one link, no bell,
  // no company switcher. Those would put an authenticated request on every
  // public page, and these pages are shared-cached (`s-maxage=60`) precisely
  // because nothing on them varies by visitor.
  //
  // `token !== null` is false during SSR and at first paint, so the server and
  // the hydrating client render the same anonymous buttons; the swap happens
  // once the boot-time refresh resolves. State change, not a mismatch.
  const isAuthenticated = useAuthStore(selectIsAuthenticated);

  const linkClass = ({ isActive }: { isActive: boolean }): string =>
    cn(
      // 13px, not the design system's `text-sm`: at 14px the seven labels
      // overrun the mockup's 269→931 link band by ~50px.
      "whitespace-nowrap rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors",
      isActive ? "text-text" : "text-text-muted hover:text-text",
    );

  return (
    // No `backdrop-blur`: at 95% `--bg` the plate is all but opaque, so the blur
    // cost a full-width compositing layer on every scroll frame to soften the
    // 5% that shows through. It was also invisible until the token colours
    // learned to take an alpha at all — the bar was fully transparent before,
    // which is the only reason a blur here ever looked like it was doing work.
    <header className="sticky top-0 z-30 bg-bg/95">
      <div className="mx-auto flex h-16 max-w-[1440px] items-center px-4 lg:px-6 xl:h-[4.75rem]">
        <Link to="/" aria-label={t("common.appName")} className="flex shrink-0 items-center">
          <BrandLogo size="lg" />
        </Link>

        <nav
          aria-label={t("public.nav.primary")}
          className="hidden min-w-0 items-center gap-0.5 xl:ms-9 xl:flex"
        >
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
              {t(item.labelKey)}
            </NavLink>
          ))}
        </nav>

        <div className="ms-auto flex items-center gap-1.5 sm:gap-2.5 xl:gap-5">
          <LanguageMenu />
          {isAuthenticated ? (
            <LinkButton to="/cabinet" size="sm" className="h-9 px-3.5">
              {t("common.cabinet")}
            </LinkButton>
          ) : (
            <>
              <Link
                to="/cabinet/login"
                className="hidden h-9 items-center rounded-md border border-border-strong px-6 text-sm font-medium text-text transition-colors hover:border-brand-line hover:bg-brand-soft sm:inline-flex"
              >
                {t("public.nav.signIn")}
              </Link>
              <LinkButton to="/cabinet/login" size="sm" className="h-9 px-3.5">
                {t("public.nav.register")}
              </LinkButton>
            </>
          )}
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("nav.openMenu")}
            aria-controls="public-nav-drawer"
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen((v) => !v)}
            className="xl:hidden"
          >
            {drawerOpen ? (
              <X size={18} strokeWidth={1.75} aria-hidden />
            ) : (
              <Menu size={18} strokeWidth={1.75} aria-hidden />
            )}
          </Button>
        </div>
      </div>

      {drawerOpen ? (
        <nav
          id="public-nav-drawer"
          aria-label={t("public.nav.primary")}
          className="border-t border-border bg-surface px-4 py-2 animate-fade-in xl:hidden"
        >
          <ul className="mx-auto flex max-w-[1440px] flex-col">
            {NAV.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  onClick={() => setDrawerOpen(false)}
                  className={({ isActive }) =>
                    cn(
                      "block rounded-md px-2 py-2.5 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-brand-soft text-brand"
                        : "text-text hover:bg-surface-2",
                    )
                  }
                >
                  {t(item.labelKey)}
                </NavLink>
              </li>
            ))}
            {/* Only anonymous: «Войти» is the one control the bar drops below
                `sm`. The signed-in «Кабинет» button never hides, so repeating
                it here would be a second copy of a visible control. */}
            {isAuthenticated ? null : (
              <li className="mt-1 border-t border-border pt-2 sm:hidden">
                <Link
                  to="/cabinet/login"
                  onClick={() => setDrawerOpen(false)}
                  className="block rounded-md px-2 py-2.5 text-sm font-medium text-text"
                >
                  {t("public.nav.signIn")}
                </Link>
              </li>
            )}
          </ul>
        </nav>
      ) : null}
    </header>
  );
}
