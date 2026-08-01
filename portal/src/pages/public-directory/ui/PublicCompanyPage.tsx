import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { selectIsAuthenticated, useAuthStore } from "@/entities/account";
import { PublicOfferTile, usePublicCompany } from "@/entities/public";
import { directoryBySlug, publicSiteOrigin } from "@/shared/config";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { Seo, useCanonical } from "@/shared/seo";
import { Badge, LinkButton, RegistryIcon, Skeleton } from "@/shared/ui";
import { useTierBase } from "@/shared/lib";

/**
 * `/{directory}/{companyId}` — a verified company's public profile.
 *
 * A company confirmed as both a manufacturer and a trader is reachable at two
 * URLs. The canonical always points at the FIRST directory the company holds a
 * role in, so the duplicate does not split the page's ranking between them.
 */
export function PublicCompanyPage({ slug }: { slug: string }) {
  const base = useTierBase();
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const { t, i18n } = useTranslation();
  const { companyId } = useParams();
  const directory = directoryBySlug(slug);
  const id = companyId && /^\d+$/.test(companyId) ? Number(companyId) : null;

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
  const facts: Array<{ label: string; value: string | null }> = [
    { label: t("public.company.legalName"), value: company.legal_name },
    { label: t("public.company.legalForm"), value: company.legal_form },
    { label: t("public.company.address"), value: company.legal_address },
    { label: t("public.company.jurisdiction"), value: company.jurisdiction },
    {
      label: t("public.company.founded"),
      value: company.founded_year ? String(company.founded_year) : null,
    },
    {
      label: t("public.company.employees"),
      value: company.employees ? String(company.employees) : null,
    },
    { label: t("public.company.productionType"), value: company.production_type },
    { label: t("public.company.iso"), value: company.iso_certification },
    {
      label: t("public.company.exportTo"),
      value: company.export_countries.length ? company.export_countries.join(", ") : null,
    },
  ];

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

  /**
   * Where «Связаться» goes once there is a session.
   *
   * Deliberately NOT the `/cabinet` twin of this page: for traders, logistics
   * and laboratories that twin is this very component, so it would link to
   * itself. The cabinet's own profile sheets are the ones carrying the action
   * bar — the manufacturer route swaps it for chat + factory RFQ, every other
   * role gets the seller route's buyer bar.
   */
  const contactTo =
    slug === "manufacturers"
      ? `/cabinet/manufacturers/${company.id}`
      : `/cabinet/sellers/${company.id}`;

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

      <div className="mx-auto max-w-[1440px] px-4 py-8 lg:px-6">
        <nav aria-label={t("public.offer.breadcrumb")} className="text-xs text-text-subtle">
          <Link to={base || "/"} className="hover:text-brand">
            {t("public.nav.home")}
          </Link>
          <span className="mx-1.5">/</span>
          <Link to={`${base}/${directory.slug}`} className="hover:text-brand">
            {t(directory.labelKey)}
          </Link>
        </nav>

        <header className="mt-5 flex flex-wrap items-start gap-4 border-b border-border pb-8">
          <span className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-surface-inset">
            {company.logo_url ? (
              <img
                src={company.logo_url}
                alt=""
                className="h-full w-full object-contain"
              />
            ) : (
              <RegistryIcon size={28} />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-semibold tracking-tight text-text">{name}</h1>
            {company.legal_address ? (
              <p className="mt-1 text-sm text-text-muted">{company.legal_address}</p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Badge variant="verified">{t("public.offer.verified")}</Badge>
              {company.roles.map((role) => (
                <Badge key={role} tone="neutral">
                  {t(`public.role.${role}`, { defaultValue: role })}
                </Badge>
              ))}
            </div>
          </div>
          {/* Anonymous still goes through the login, but comes out at the same
              place rather than at the cabinet home. */}
          <LinkButton
            to={isAuthenticated ? contactTo : "/cabinet/login"}
            state={isAuthenticated ? undefined : { from: contactTo }}
          >
            {t("public.company.contact")}
          </LinkButton>
        </header>

        <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <section aria-labelledby="company-offers">
            <div className="flex items-baseline justify-between gap-4">
              <h2 id="company-offers" className="text-lg font-semibold text-text">
                {t("public.company.products")}
              </h2>
              {company.offer_count > company.offers.length ? (
                <Link
                  to={`${base}/market?seller_company_id=${company.id}`}
                  className="shrink-0 text-sm text-brand hover:underline"
                >
                  {t("public.home.seeAll")}
                </Link>
              ) : null}
            </div>

            {company.offers.length > 0 ? (
              <ul className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {company.offers.map((offer) => (
                  <li key={offer.id} className="min-w-0">
                    <PublicOfferTile offer={offer} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 rounded-lg border border-border bg-surface px-4 py-10 text-center text-sm text-text-muted">
                {t("public.company.noProducts")}
              </p>
            )}
          </section>

          <aside>
            <h2 className="text-lg font-semibold text-text">{t("public.company.about")}</h2>
            {company.main_products ? (
              <p className="mt-3 text-sm leading-relaxed text-text-muted">
                {company.main_products}
              </p>
            ) : null}
            <dl className="mt-4 space-y-3 border-t border-border pt-4">
              {facts
                .filter((f) => f.value)
                .map((fact) => (
                  <div key={fact.label}>
                    <dt className="text-xs text-text-subtle">{fact.label}</dt>
                    <dd className="mt-0.5 text-sm text-text">{fact.value}</dd>
                  </div>
                ))}
            </dl>
          </aside>
        </div>
      </div>
    </>
  );
}
