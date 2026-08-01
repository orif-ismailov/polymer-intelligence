import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { offerImageUrl } from "@/entities/market";
import { offerPhotoFiles } from "@/shared/config";
import {
  Badge,
  CheckCircleIcon,
  ChevronRightIcon,
  EmptyState,
  ImageIcon,
  PackageOpenIcon,
} from "@/shared/ui";

import type { CompanyProfileOffer } from "../model/types";

interface ProfileProductsTabProps {
  offers: CompanyProfileOffer[];
  offerCount: number;
  /**
   * Where a product row goes — always `/market/:id`, but the caller decides the
   * query string: a manufacturer profile appends `?fromManufacturer=1` so the
   * product sheet offers factory chat + RFQ instead of the trader inquiry form.
   */
  productHref: (offer: CompanyProfileOffer) => string;
  /** «Показать все» target; omit to hide the link. */
  seeAllHref?: string;
}

/**
 * «Продукты» — vertical list matching the mockup: thumb · name · CAS · stock · chevron.
 *
 * Rows are `<Link>`s, not `<button onClick={navigate}>`. Client-side navigation
 * is identical either way, but only one of them is a real `href` — openable in a
 * new tab, and followable by a crawler on the storefront, which is the whole
 * reason `PublicOfferTile` had to exist separately from the cabinet's card.
 */
export function ProfileProductsTab({
  offers,
  offerCount,
  productHref,
  seeAllHref,
}: ProfileProductsTabProps) {
  const { t } = useTranslation();

  if (offers.length === 0) {
    return (
      <EmptyState
        icon={<PackageOpenIcon size={28} />}
        title={t("companyProfile.productsEmpty")}
        description={t("companyProfile.productsEmptyBody")}
      />
    );
  }

  return (
    <div className="space-y-3" data-testid="seller-profile-products">
      <h3 className="text-sm font-semibold text-text">{t("companyProfile.mainProducts")}</h3>
      <div className="space-y-2">
        {offers.map((offer) => {
          const title = offer.product_text ?? offer.grade_text ?? "—";
          const subtitle =
            offer.polymer_type ??
            (offer.product_text && offer.grade_text ? offer.grade_text : null);
          const cover = offerPhotoFiles(offer.files)[0] ?? null;
          return (
            <Link
              key={offer.id}
              to={productHref(offer)}
              className="flex w-full items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5 text-left transition-colors hover:border-brand-line hover:bg-surface-2"
            >
              <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-surface-inset">
                {cover ? (
                  <img
                    src={offerImageUrl(offer.id, cover.id)}
                    alt=""
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <ImageIcon size={20} className="text-text-subtle" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-text">{title}</p>
                {subtitle ? (
                  <p className="truncate text-xs text-text-muted">{subtitle}</p>
                ) : null}
                {offer.cas_number ? (
                  <p className="num mt-0.5 text-xs text-text-subtle">CAS: {offer.cas_number}</p>
                ) : null}
                <div className="mt-1">
                  <Badge
                    tone={offer.availability === "in_stock" ? "success" : "neutral"}
                    icon={
                      offer.availability === "in_stock" ? <CheckCircleIcon /> : undefined
                    }
                  >
                    {t(`availability.${offer.availability}`)}
                  </Badge>
                </div>
              </div>
              <ChevronRightIcon size={16} className="shrink-0 text-text-subtle" />
            </Link>
          );
        })}
      </div>
      {offerCount > offers.length && seeAllHref ? (
        <Link
          to={seeAllHref}
          className="block w-full rounded-md border border-border px-3 py-2.5 text-center text-sm font-medium text-brand transition-colors hover:border-brand-line hover:bg-brand-soft"
        >
          {t("companyProfile.seeAllProducts", { count: offerCount })}
        </Link>
      ) : null}
    </div>
  );
}
