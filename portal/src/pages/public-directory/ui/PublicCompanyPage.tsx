import { useState } from "react";

import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { selectIsAuthenticated, useAuthStore } from "@/entities/account";
import { useCompanies } from "@/entities/company";
import { usePublicCompany } from "@/entities/public";
import {
  COMPANY_PROFILE_TAB_IDS,
  CompanyProfileView,
  ProfileActionBar,
  type CompanyProfileTabId,
} from "@/features/company-profile";
import { directoryBySlug, publicSiteOrigin } from "@/shared/config";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { useTierBase } from "@/shared/lib";
import { Seo, useCanonical } from "@/shared/seo";
import { LinkButton, Skeleton, StickyActionBar } from "@/shared/ui";

/**
 * `/{directory}/{companyId}` — a verified company's public profile.
 *
 * Renders the same sheet as the cabinet's `/cabinet/sellers/:id` and
 * `/cabinet/sellers/:id` (`features/company-profile`), not a simplified copy of
 * it. What the tiers do not share is what a session buys: the cabinet's footer
 * opens a chat or an RFQ, and here there is one «Связаться» link that goes
 * through the login when there is no session yet.
 *
 * Also mounted under `/cabinet` for the three non-manufacturer directories,
 * which is why the internal links go through `useTierBase()`.
 *
 * A company confirmed as both a manufacturer and a trader is reachable at two
 * URLs. The canonical always points at the FIRST directory the company holds a
 * role in, so the duplicate does not split the page's ranking between them.
 */
export function PublicCompanyPage({ slug }: { slug: string }) {
  const base = useTierBase();
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  // Gated on the session: this page server-renders for anonymous visitors, and
  // an unguarded GET /portal/companies would fire from Node on every render.
  const { data: companies = [] } = useCompanies(isAuthenticated);
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { companyId } = useParams();
  const directory = directoryBySlug(slug);
  const id = companyId && /^\d+$/.test(companyId) ? Number(companyId) : null;
  const [tab, setTab] = useState<CompanyProfileTabId>(COMPANY_PROFILE_TAB_IDS[0]);

  const origin = publicSiteOrigin();
  const query = usePublicCompany(directory?.slug ?? "", directory ? id : null);
  const company = query.data;

  // Canonical is computed from the company's own roles, not from the URL that
  // was followed, so `/traders/12` and `/manufacturers/12` agree on one address.
  const canonicalSlug =
    company?.roles
      ?.map((role) => (role === "manufacturer" ? "manufacturers" : role === "trader" ? "traders" : role === "logistics_provider" ? "logistics" : role === "laboratory" ? "laboratories" : null))
      .find(Boolean) ?? directory?.slug ?? "";
  const { canonical, alternates } = useCanonical(
    origin,
    `/${canonicalSlug}/${id ?? ""}`,
    SUPPORTED_LANGS,
    i18n.language,
  );

  if (!directory || id == null) {
    return (
      <div className="mx-auto max-w-[1440px] px-4 py-20 text-center lg:px-6">
        <h1 className="text-2xl font-semibold text-text">{t("public.company.notFound")}</h1>
        <div className="mt-6">
          <LinkButton to={base || "/"} variant="outline">
            {t("public.nav.home")}
          </LinkButton>
        </div>
      </div>
    );
  }

  // Metadata ships even while the data is in flight. A crawler that arrives
  // during a slow upstream must still get a canonical and a title, or the URL
  // is indexed with whatever the template's fallback said.
  const pendingSeo = (
    <Seo
      title={t(directory.labelKey)}
      description={t(directory.subtitleKey)}
      canonical={canonical}
      alternates={alternates}
    />
  );

  if (query.isLoading) {
    return (
      <div className="mx-auto max-w-[1440px] px-4 py-10 lg:px-6">
        {pendingSeo}
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (query.isError || !company) {
    return (
      <div className="mx-auto max-w-[1440px] px-4 py-20 text-center lg:px-6">
        <Seo title={t("public.company.notFound")} noindex />
        <h1 className="text-2xl font-semibold text-text">{t("public.company.notFound")}</h1>
        <p className="mt-2 text-sm text-text-muted">{t("public.company.notFoundBody")}</p>
        <div className="mt-6">
          <LinkButton to={`${base}/${directory.slug}`} variant="outline">
            {t(directory.labelKey)}
          </LinkButton>
        </div>
      </div>
    );
  }

  const name = company.short_name ?? company.legal_name ?? t("public.company.untitled");

  const jsonLd: Array<Record<string, unknown>> = [
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: company.legal_name ?? name,
      alternateName: company.short_name ?? undefined,
      url: canonical,
      ...(company.logo_url ? { logo: `${origin}${company.logo_url}` } : {}),
      ...(company.legal_address
        ? {
            address: {
              "@type": "PostalAddress",
              streetAddress: company.legal_address,
              addressCountry: company.jurisdiction,
            },
          }
        : {}),
      ...(company.founded_year ? { foundingDate: String(company.founded_year) } : {}),
    },
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: t("public.nav.home"), item: `${origin}/` },
        {
          "@type": "ListItem",
          position: 2,
          name: t(directory.labelKey),
          item: `${origin}/${directory.slug}`,
        },
        { "@type": "ListItem", position: 3, name, item: canonical },
      ],
    },
  ];

  /*
   * There is no `/cabinet` twin to send anyone to — this URL is the profile for
   * everyone. Anonymous visitors go through the login and come back HERE, where
   * `isOwner`/`isAuthenticated` then decide which footer they get.
   */
  const isManufacturer = slug === "manufacturers";
  const isOwner = companies.some((c) => c.id === company.id);
  const selfHref = `${base}/${directory.slug}/${company.id}`;

  return (
    <>
      <Seo
        title={t("public.company.metaTitle", { name, directory: t(directory.labelKey) })}
        description={
          company.main_products ??
          t("public.company.metaDescription", { name, country: company.jurisdiction })
        }
        canonical={canonical}
        alternates={alternates}
        ogType="profile"
        ogImage={company.logo_url ? `${origin}${company.logo_url}` : undefined}
        jsonLd={jsonLd}
      />

      {/* `max-w-6xl`, not the storefront's usual `max-w-[1440px]`: the sheet is
          laid out for the cabinet's column width (`AppShell`). */}
      <div className="mx-auto max-w-6xl px-4 py-8 lg:px-6">
        <nav aria-label={t("public.offer.breadcrumb")} className="text-xs text-text-subtle">
          <Link to={base || "/"} className="hover:text-brand">
            {t("public.nav.home")}
          </Link>
          <span className="mx-1.5">/</span>
          <Link to={`${base}/${directory.slug}`} className="hover:text-brand">
            {t(directory.labelKey)}
          </Link>
        </nav>

        <div className="mt-5">
          <CompanyProfileView
            company={company}
            backTo={`${base}/${directory.slug}`}
            tab={tab}
            onTabChange={setTab}
            /* Not `${base}/market/…`: the cabinet twin of the product sheet is
               gone, so there is one address for a listing in either tier.
               `?fromManufacturer=1` is what makes that sheet offer factory chat
               + RFQ instead of the trader inquiry form. */
            productHref={(offer) =>
              `/market/${offer.id}${isManufacturer ? "?fromManufacturer=1" : ""}`
            }
            seeAllHref={`/market?seller_company_id=${company.id}`}
            // Every panel in the HTML: this is a company's landing page, and its
            // facts live in the About panel.
            renderAllPanels
            headerActions={
              /* Anonymous still goes through the login, but comes back to this
                 same page rather than to the cabinet home. Replaced by the real
                 footer once there is a session. */
              isAuthenticated ? null : (
                <LinkButton
                  size="lg"
                  fullWidth
                  to="/cabinet/login"
                  state={{ from: selfHref }}
                >
                  {t("public.company.contact")}
                </LinkButton>
              )
            }
            /* Mounts after hydration only — see `useOfferSession`'s note; the
               same reasoning applies to every authed surface on the storefront. */
            actionBar={
              !isAuthenticated ? null : isOwner ? (
                <StickyActionBar>
                  <div className="flex w-full gap-2" data-testid="company-owner-actions">
                    <LinkButton
                      variant="outline"
                      size="lg"
                      className="min-w-0 flex-1"
                      to={`/cabinet/companies/${company.id}/manage`}
                    >
                      {t("company.manage")}
                    </LinkButton>
                    <LinkButton size="lg" className="min-w-0 flex-[1.4]" to="/cabinet/offers/new">
                      {t("company.createOffer")}
                    </LinkButton>
                  </div>
                </StickyActionBar>
              ) : (
                <ProfileActionBar
                  mode={isManufacturer ? "manufacturer" : "seller"}
                  messageDisabled={!isManufacturer && company.offer_count === 0}
                  onMessage={() => {
                    if (isManufacturer) {
                      void navigate(`/cabinet/manufacturers/${company.id}/chat`);
                      return;
                    }
                    setTab("products");
                  }}
                  onRfq={() => setTab("products")}
                />
              )
            }
            footerNote={
              isAuthenticated && !isOwner && tab === "products" ? (
                <p className="text-center text-xs text-text-subtle">
                  {t("companyProfile.pickOfferHint")}
                </p>
              ) : null
            }
          />
        </div>
      </div>
    </>
  );
}
