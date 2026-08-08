import { useState } from "react";

import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { useToggleFavorite } from "@/entities/market";
import { publicOfferImageUrl, usePublicOffer } from "@/entities/public";
import {
  OfferActionBar,
  OfferCompatibilityPanel,
  OfferDescriptionBlocks,
  OfferDocuments,
  OfferHero,
  OfferInquiryCard,
  OfferReviewsPanel,
  OfferSpecs,
  PRODUCT_DETAIL_TAB_IDS,
  useOfferSession,
  type ProductDetailTabId,
} from "@/features/product-detail";
import { SampleRequestForm } from "@/features/sample-request";
import {
  directoryForRoles,
  offerDocumentFiles,
  offerPhotoFiles,
  publicSiteOrigin,
} from "@/shared/config";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { Seo, useCanonical } from "@/shared/seo";
import {
  Button,
  HeartIcon,
  LinkButton,
  SendIcon,
  Skeleton,
  Tabs,
  type TabItem,
} from "@/shared/ui";

/**
 * `/market/:offerId` — a listing's public page, and the marketplace's main
 * search-landing surface.
 *
 * The same URL and the same product sheet for everyone: this renders the exact
 * components the cabinet sheets do (`features/product-detail`), not a
 * simplified copy of them. Anonymous visitors get the full listing and a prompt
 * to sign in before contacting the seller. What is behind the login is the
 * ability to ACT, not the ability to read, which is the only version of this
 * that can rank.
 *
 * There is no `/cabinet` twin any more — this is the only product sheet. Two
 * things follow, and both are forced:
 *
 * 1. **Every panel is rendered, inactive ones behind `hidden`.** The whole sheet
 *    has to reach a crawler in the server HTML, and specs is where the
 *    manufacturer, HS code and applications live. `hidden` decides what is on
 *    screen, not what shipped.
 * 2. **The actions mount after hydration, never on the server** (`useOfferSession`).
 *    Their enabled states answer "is YOUR company verified" — authenticated
 *    questions — and this HTML is shared-cached (`s-maxage=60`) precisely
 *    because nothing in it varies by visitor. The server render is deterministically
 *    anonymous, so the actions arrive as a state change rather than as a
 *    hydration mismatch, exactly the contract `PublicTopNav` already lives under.
 */
export function PublicOfferPage() {
  const { t, i18n } = useTranslation();
  const { offerId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Arrived from the manufacturers directory — swap the trader inquiry door for
  // a direct chat + factory RFQ (`docs/new-design/manufacturer_flow.jpeg`).
  const fromManufacturer = searchParams.get("fromManufacturer") === "1";
  const id = offerId && /^\d+$/.test(offerId) ? Number(offerId) : null;
  const [tab, setTab] = useState<ProductDetailTabId>("description");
  const [sampleSent, setSampleSent] = useState(false);

  const session = useOfferSession(id);
  const toggleFavorite = useToggleFavorite();

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
  const sellerDirectory = directoryForRoles(offer.business_roles);
  const photos = offerPhotoFiles(offer.files);
  const documents = offerDocumentFiles(offer.files);
  const passport = offer.files.find((f) => f.kind === "lab_passport") ?? null;
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

  const tabs: TabItem[] = PRODUCT_DETAIL_TAB_IDS.map((tabId) => ({
    id: tabId,
    label: t(`market.tabs.${tabId}`),
    ...(tabId === "documents" && documents.length > 0 ? { count: documents.length } : {}),
  }));

  const canInquire = session != null && session.companyId != null && !session.offer.is_own;
  const canSendRfq = canInquire && session?.offer.accepts_rfq === true;

  // Both sides must be verified or POST /portal/contracts answers 422, and a TG-origin
  // offer has no company to sign with at all. Say which of those it is, on the page,
  // rather than letting the buyer discover it two screens later.
  const contractBlockedReason = !session
    ? null
    : !session.offer.accepts_contract
      ? t("market.detail.contractNotOffered")
      : session.offer.seller_company_id == null || !session.offer.company_verified
        ? t("market.detail.contractNeedsVerifiedSeller")
        : session.activeCompany?.status !== "verified"
          ? t("market.detail.contractNeedsVerifiedCompany")
          : null;

  function scrollTo(elementId: string): void {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    // The smooth variant is an animation, and an animation can silently never
    // run — hidden documents pause rAF, and a click racing a re-render can drop
    // it — which left «Написать продавцу» looking dead. If nothing has moved
    // shortly after, jump instantly instead.
    const startY = window.scrollY;
    window.setTimeout(() => {
      if (
        Math.abs(window.scrollY - startY) < 1 &&
        Math.abs(el.getBoundingClientRect().top) > 80
      ) {
        el.scrollIntoView({ block: "start" });
      }
    }, 250);
    // Land the cursor in the form the click promised: visible proof the tap
    // did something, and the same landing a screen reader needs.
    el.querySelector<HTMLElement>("input, textarea, select")?.focus({ preventScroll: true });
  }

  /*
   * Reading is public; acting is not. There is no cabinet twin to send anyone to
   * any more — this URL is both — so the anonymous CTA goes through the login and
   * comes back to THIS page, where `session` will then be non-null and the real
   * actions take its place.
   */
  const cta = session ? (
    <>
      <Button
        size="lg"
        fullWidth
        disabled={!canSendRfq}
        onClick={() => {
          if (fromManufacturer && session.offer.seller_company_id != null) {
            void navigate(
              `/cabinet/manufacturers/${session.offer.seller_company_id}/rfq/${offer.id}`,
            );
            return;
          }
          setTab("description");
          window.setTimeout(() => scrollTo("inquiry"), 50);
        }}
        data-testid="product-detail-rfq"
      >
        <SendIcon size={16} />
        {t("market.detail.requestRfq")}
      </Button>
      <Button
        size="lg"
        variant="outline"
        fullWidth
        aria-pressed={session.offer.is_favorite}
        onClick={() =>
          toggleFavorite.mutate({ offerId: offer.id, next: !session.offer.is_favorite })
        }
        data-testid="product-detail-favorite"
      >
        <HeartIcon
          size={16}
          className={session.offer.is_favorite ? "text-danger" : undefined}
        />
        {t(session.offer.is_favorite ? "market.unfavorite" : "market.detail.addFavorite")}
      </Button>
    </>
  ) : (
    <LinkButton
      size="lg"
      fullWidth
      to="/cabinet/login"
      state={{ from: `/market/${offer.id}` }}
    >
      {t("public.offer.signInToContact")}
    </LinkButton>
  );

  return (
    <>
      <Seo
        title={metaTitle}
        description={metaDescription}
        canonical={canonical}
        alternates={alternates}
        ogType="product"
        ogImage={photos[0] ? `${origin}${publicOfferImageUrl(offer.id, photos[0].id)}` : undefined}
        jsonLd={jsonLd}
      />

      {/* `max-w-6xl`, not the storefront's usual `max-w-[1440px]`: the sheet is
          laid out for the cabinet's column width (`AppShell`), and stretching it
          to 1440 blows the gallery up and strands the fact column beside it. */}
      {/* `pb-36 md:pb-0` whenever the sticky bar is up, or it covers the last
          card — a failure mode no test can see. */}
      <div
        className={`mx-auto max-w-6xl px-4 py-8 lg:px-6 ${session ? "pb-36 md:pb-8" : ""}`}
        data-testid="product-detail"
      >
        <nav aria-label={t("public.offer.breadcrumb")} className="text-xs text-text-subtle">
          <Link to="/" className="hover:text-brand">
            {t("public.nav.home")}
          </Link>
          <span className="mx-1.5">/</span>
          <Link to="/market" className="hover:text-brand">
            {t("public.market.title")}
          </Link>
        </nav>

        <div className="mt-5 space-y-5">
          <OfferHero offer={offer} photos={photos} actions={cta} />
          {session ? null : (
            <p className="-mt-3 text-xs text-text-subtle">{t("public.offer.contactHint")}</p>
          )}

          <Tabs
            items={tabs}
            value={tab}
            onChange={(id) => setTab(id as ProductDetailTabId)}
            variant="underlineGold"
            label={title}
          />

          {/* All five panels ship in the HTML — see the note on this component. */}
          <Panel active={tab === "description"}>
            <OfferDescriptionBlocks
              offer={offer}
              documents={documents}
              passport={passport}
              sellerHref={
                // The profile endpoint is scoped to the directory in the path,
                // so the slug must come from the seller's own confirmed roles —
                // a trader linked under /manufacturers 404s.
                offer.seller_company_id != null && sellerDirectory
                  ? `/${sellerDirectory.slug}/${offer.seller_company_id}`
                  : null
              }
              isOwn={session?.offer.is_own ?? false}
              onRequestSample={session ? () => scrollTo("samples") : null}
              sampleSlot={
                session && session.companyId != null ? (
                  sampleSent ? (
                    <p className="text-sm text-success">{t("samples.sentOk")}</p>
                  ) : (
                    <SampleRequestForm
                      offerId={offer.id}
                      companyId={session.companyId}
                      onSent={() => setSampleSent(true)}
                    />
                  )
                ) : null
              }
            />
          </Panel>
          <Panel active={tab === "specs"}>
            <OfferSpecs offer={offer} />
          </Panel>
          <Panel active={tab === "documents"}>
            <OfferDocuments offerId={offer.id} documents={documents} />
          </Panel>
          <Panel active={tab === "compatibility"}>
            <OfferCompatibilityPanel />
          </Panel>
          <Panel active={tab === "reviews"}>
            <OfferReviewsPanel />
          </Panel>

          {/* Everything below mounts only once there is a session — after
              hydration, never in the cached HTML. */}
          {session ? (
            <>
              <OfferInquiryCard offer={session.offer} companyId={session.companyId} />
              <OfferActionBar
                canAct={canInquire}
                acceptsRfq={session.offer.accepts_rfq}
                acceptsEscrow={session.offer.accepts_escrow}
                contractBlockedReason={contractBlockedReason}
                onMessage={() => {
                  if (fromManufacturer && session.offer.seller_company_id != null) {
                    void navigate(
                      `/cabinet/manufacturers/${session.offer.seller_company_id}/chat`,
                    );
                    return;
                  }
                  setTab("description");
                  window.setTimeout(() => scrollTo("inquiry"), 50);
                }}
                onContract={() =>
                  void navigate(
                    `/cabinet/contracts/new?offerId=${offer.id}&counterpartyId=${session.offer.seller_company_id}`,
                  )
                }
              />
            </>
          ) : null}
        </div>
      </div>
    </>
  );
}

/**
 * The `hidden` ATTRIBUTE, not a Tailwind `hidden` class: a `display` utility on
 * the same element would override the attribute, and this wrapper carries no
 * classes precisely so nothing can.
 *
 * No `role="tabpanel"` — `Tabs` is deliberately a `role="group"` of `aria-pressed`
 * toggles rather than a tablist (see the primitive), and half a tab pattern is an
 * axe violation where a plain toggle is not.
 */
function Panel({ active, children }: { active: boolean; children: React.ReactNode }) {
  return <div hidden={!active}>{children}</div>;
}
