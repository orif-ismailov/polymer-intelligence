import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { selectIsAuthenticated, useAuthStore } from "@/entities/account";
import { publicOfferImageUrl, usePublicOffer } from "@/entities/public";
import { publicSiteOrigin } from "@/shared/config";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { Seo, useCanonical } from "@/shared/seo";
import { Badge, ImageIcon, LinkButton, Skeleton } from "@/shared/ui";

/**
 * `/market/:offerId` — a listing's public page, and the marketplace's main
 * search-landing surface.
 *
 * The same URL for everyone. Anonymous visitors get the full listing and a
 * prompt to sign in before contacting the seller; signed-in visitors get the
 * inquiry action. What is behind the login is the ability to ACT, not the
 * ability to read, which is the only version of this that can rank.
 */
export function PublicOfferPage() {
  const { t, i18n } = useTranslation();
  const { offerId } = useParams();
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const id = offerId && /^\d+$/.test(offerId) ? Number(offerId) : null;

  const origin = publicSiteOrigin();
  const { canonical, alternates } = useCanonical(
    origin,
    `/market/${id ?? ""}`,
    SUPPORTED_LANGS,
    i18n.language,
  );

  const query = usePublicOffer(id);
  const offer = query.data;

  if (query.isLoading) {
    return (
      <div className="mx-auto max-w-[1440px] px-4 py-10 lg:px-6">
        {/* Canonical ships even while the listing is in flight. A crawler that
            arrives during a slow upstream must not index this URL under the
            template's generic fallback title. */}
        <Seo title={t("public.market.title")} canonical={canonical} alternates={alternates} />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (query.isError || !offer) {
    return (
      <div className="mx-auto max-w-[1440px] px-4 py-20 text-center lg:px-6">
        <Seo title={t("public.offer.notFound")} noindex />
        <h1 className="text-2xl font-semibold text-text">{t("public.offer.notFound")}</h1>
        <p className="mt-2 text-sm text-text-muted">{t("public.offer.notFoundBody")}</p>
        <div className="mt-6">
          <LinkButton to="/market" variant="outline">
            {t("public.market.title")}
          </LinkButton>
        </div>
      </div>
    );
  }

  const title = offer.product_text ?? offer.grade_text ?? t("public.offer.untitled");
  const photos = offer.files.filter((f) => f.kind === "photo");
  const location = [offer.warehouse_city, offer.country].filter(Boolean).join(", ");
  const metaTitle = t("public.offer.metaTitle", {
    name: title,
    seller: offer.display_name ?? "IMEX AI",
  });
  const metaDescription =
    offer.description?.slice(0, 160) ??
    t("public.offer.metaDescription", { name: title, location: location || "-" });

  const jsonLd: Array<Record<string, unknown>> = [
    {
      "@context": "https://schema.org",
      "@type": "Product",
      name: title,
      sku: String(offer.id),
      description: offer.description ?? metaDescription,
      ...(offer.manufacturer ? { brand: { "@type": "Brand", name: offer.manufacturer } } : {}),
      ...(photos.length > 0
        ? { image: photos.map((p) => `${origin}${publicOfferImageUrl(offer.id, p.id)}`) }
        : {}),
      ...(offer.price
        ? {
            offers: {
              "@type": "Offer",
              price: offer.price,
              priceCurrency: offer.currency,
              availability:
                offer.availability === "in_stock"
                  ? "https://schema.org/InStock"
                  : "https://schema.org/PreOrder",
              url: canonical,
              ...(offer.seller_display_name
                ? { seller: { "@type": "Organization", name: offer.seller_display_name } }
                : {}),
            },
          }
        : {}),
    },
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: t("public.nav.home"), item: `${origin}/` },
        {
          "@type": "ListItem",
          position: 2,
          name: t("public.market.title"),
          item: `${origin}/market`,
        },
        { "@type": "ListItem", position: 3, name: title, item: canonical },
      ],
    },
  ];

  const specs: Array<{ label: string; value: string | null }> = [
    { label: t("public.offer.grade"), value: offer.grade_text },
    { label: t("public.offer.polymer"), value: offer.polymer_type },
    { label: t("public.offer.cas"), value: offer.cas_number },
    { label: t("public.offer.hs"), value: offer.hs_code },
    { label: t("public.offer.manufacturer"), value: offer.manufacturer },
    { label: t("public.offer.incoterms"), value: offer.incoterms },
    {
      label: t("public.offer.moq"),
      value: offer.min_order_qty ? `${offer.min_order_qty} ${offer.qty_unit}` : null,
    },
    {
      label: t("public.offer.leadTime"),
      value: offer.lead_time_days == null ? null : String(offer.lead_time_days),
    },
    { label: t("public.offer.location"), value: location || null },
  ];

  return (
    <>
      <Seo
        title={metaTitle}
        description={metaDescription}
        canonical={canonical}
        alternates={alternates}
        ogType="product"
        ogImage={
          photos[0] ? `${origin}${publicOfferImageUrl(offer.id, photos[0].id)}` : undefined
        }
        jsonLd={jsonLd}
      />

      <div className="mx-auto max-w-[1440px] px-4 py-8 lg:px-6">
        <nav aria-label={t("public.offer.breadcrumb")} className="text-xs text-text-subtle">
          <Link to="/" className="hover:text-brand">
            {t("public.nav.home")}
          </Link>
          <span className="mx-1.5">/</span>
          <Link to="/market" className="hover:text-brand">
            {t("public.market.title")}
          </Link>
        </nav>

        <div className="mt-5 grid gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div>
            <div className="aspect-[4/3] overflow-hidden rounded-lg border border-border bg-surface-inset">
              {photos[0] ? (
                <img
                  src={publicOfferImageUrl(offer.id, photos[0].id)}
                  alt={title}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-text-subtle">
                  <ImageIcon size={40} />
                </div>
              )}
            </div>
            {photos.length > 1 ? (
              <ul className="mt-3 grid grid-cols-4 gap-3">
                {photos.slice(1, 5).map((photo) => (
                  <li
                    key={photo.id}
                    className="aspect-square overflow-hidden rounded-md border border-border bg-surface-inset"
                  >
                    <img
                      src={publicOfferImageUrl(offer.id, photo.id)}
                      alt=""
                      loading="lazy"
                      className="h-full w-full object-cover"
                    />
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={offer.availability === "in_stock" ? "in-stock" : "on-order"}>
                {t(`availability.${offer.availability}`)}
              </Badge>
              {offer.lab_verified ? (
                <Badge variant="lab-verified">{t("public.offer.labVerified")}</Badge>
              ) : offer.has_lab_passport ? (
                <Badge tone="neutral">{t("public.offer.labPassport")}</Badge>
              ) : null}
              {offer.company_verified ? (
                <Badge variant="verified">{t("public.offer.verified")}</Badge>
              ) : null}
            </div>

            <h1 className="mt-3 text-2xl font-semibold leading-tight tracking-tight text-text">
              {title}
            </h1>

            <p className="mt-4">
              {offer.price == null ? (
                <span className="text-xl font-semibold text-text-muted">
                  {t("public.offer.onRequest")}
                </span>
              ) : (
                <span className="num text-3xl font-semibold leading-tight text-brand">
                  {offer.price}{" "}
                  <span className="text-base font-medium text-text-muted">
                    {offer.currency}
                    {offer.qty_unit ? `/${offer.qty_unit}` : ""}
                  </span>
                </span>
              )}
            </p>

            {offer.seller_company_id ? (
              <p className="mt-3 text-sm text-text-muted">
                {t("public.offer.soldBy")}{" "}
                <Link
                  to={`/manufacturers/${offer.seller_company_id}`}
                  className="text-brand hover:underline"
                >
                  {offer.seller_display_name ?? offer.display_name}
                </Link>
              </p>
            ) : offer.display_name ? (
              <p className="mt-3 text-sm text-text-muted">
                {t("public.offer.soldBy")} {offer.display_name}
              </p>
            ) : null}

            {/*
             * Reading is public; contacting the seller is not. Both branches
             * therefore end up in the cabinet, where the inquiry form and the
             * buyer's identity live — the difference is only whether the
             * visitor stops at the login on the way. `state.from` is what
             * carries them past it to THIS listing instead of the cabinet home
             * (`LoginPage` forwards it to the OTP step, which navigates to it).
             */}
            <div className="mt-6">
              {isAuthenticated ? (
                <LinkButton to={`/cabinet/market/${offer.id}`}>
                  {t("public.offer.sendInquiry")}
                </LinkButton>
              ) : (
                <>
                  <LinkButton
                    to="/cabinet/login"
                    state={{ from: `/cabinet/market/${offer.id}` }}
                  >
                    {t("public.offer.signInToContact")}
                  </LinkButton>
                  <p className="mt-2 text-xs text-text-subtle">
                    {t("public.offer.contactHint")}
                  </p>
                </>
              )}
            </div>

            <dl className="mt-8 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-border pt-6">
              {specs
                .filter((s) => s.value)
                .map((spec) => (
                  <div key={spec.label}>
                    <dt className="text-xs text-text-subtle">{spec.label}</dt>
                    <dd className="num mt-0.5 text-sm text-text">{spec.value}</dd>
                  </div>
                ))}
            </dl>

            {offer.key_properties.length > 0 ? (
              <div className="mt-6">
                <h2 className="text-sm font-semibold text-text">
                  {t("public.offer.properties")}
                </h2>
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {offer.key_properties.map((prop) => (
                    <li
                      key={prop}
                      className="rounded-full border border-border px-2.5 py-0.5 text-xs text-text-muted"
                    >
                      {prop}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {offer.applications.length > 0 ? (
              <div className="mt-5">
                <h2 className="text-sm font-semibold text-text">
                  {t("public.offer.applications")}
                </h2>
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {offer.applications.map((app) => (
                    <li
                      key={app}
                      className="rounded-full border border-border px-2.5 py-0.5 text-xs text-text-muted"
                    >
                      {app}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {offer.description ? (
              <div className="mt-6 border-t border-border pt-6">
                <h2 className="text-sm font-semibold text-text">
                  {t("public.offer.description")}
                </h2>
                <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-text-muted">
                  {offer.description}
                </p>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}
