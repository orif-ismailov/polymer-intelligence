import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";

import { LabBadges } from "@/entities/lab";
import { coerceLang } from "@/shared/i18n";
import { countryName, formatMoney } from "@/shared/lib";
import { Badge, Card, CardBody, CheckCircleIcon } from "@/shared/ui";

import type { ProductDetailFile, ProductDetailOffer } from "../model/types";

import { OfferGallery } from "./OfferGallery";

interface OfferHeroProps {
  offer: ProductDetailOffer;
  photos: ProductDetailFile[];
  onPhotoChange?: (index: number) => void;
  /**
   * The CTA row under the gallery.
   *
   * A slot rather than derived state: the cabinet's two buttons read
   * `is_favorite` and `accepts_rfq`, neither of which the public payload
   * carries, and the storefront wants one sign-in link instead. Passing the
   * buttons in is what keeps every session-dependent branch in the page and
   * lets this component server-render on the storefront.
   */
  actions?: ReactNode;
}

/**
 * The product-detail hero (`docs/new-design/product_detail.jpeg`): swipeable
 * gallery, title / price / badges, and the full-width CTAs under the strip
 * (not squeezed into the narrow side column).
 *
 * Renders the page's `<h1>` — a caller that adds its own has two.
 */
export function OfferHero({ offer, photos, onPhotoChange, actions }: OfferHeroProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const title = offer.product_text ?? offer.grade_text ?? "—";
  const subtitle = offer.polymer_type ?? offer.grade_text ?? null;
  const country = offer.country ? countryName(offer.country, lang) : null;
  const terms = [offer.incoterms, country].filter(Boolean).join(", ");

  return (
    <Card data-testid="product-detail-hero">
      <CardBody className="space-y-4">
        <div className="grid gap-4 md:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] md:items-start">
          <OfferGallery
            offerId={offer.id}
            photos={photos}
            labVerified={offer.lab_verified}
            alt={title}
            onActiveIndexChange={onPhotoChange}
          />

          <div className="flex min-w-0 flex-col gap-3">
            <div>
              <h1 className="text-2xl font-semibold leading-tight text-text">{title}</h1>
              {subtitle && subtitle !== title ? (
                <p className="mt-1 text-sm text-text-muted">{subtitle}</p>
              ) : null}
            </div>

            <div className="flex flex-wrap gap-2">
              <Badge
                tone={offer.availability === "in_stock" ? "success" : "neutral"}
                icon={
                  offer.availability === "in_stock" ? (
                    <CheckCircleIcon />
                  ) : undefined
                }
              >
                {t(`availability.${offer.availability}`)}
              </Badge>
              <LabBadges hasLabPassport={offer.has_lab_passport} labVerified={offer.lab_verified} />
            </div>

            <div>
              {offer.price == null ? (
                <p className="text-2xl font-semibold text-text-muted">{t("market.onRequest")}</p>
              ) : (
                <p className="num text-2xl font-semibold leading-tight text-text">
                  {formatMoney(offer.price, offer.currency, lang)}
                  <span className="ms-1 text-base font-medium text-text-muted">
                    / {offer.qty_unit}
                  </span>
                </p>
              )}
              {terms ? <p className="mt-1 text-sm text-text-muted">{terms}</p> : null}
            </div>
          </div>
        </div>

        {/* Full-width CTAs — matching the mockup row under the hero, not crammed
            into the half-width info column beside the gallery. Flex rather than a
            2-column grid so the row fits whatever the tier passes: the cabinet's
            two buttons share it, the storefront's single CTA spans it. */}
        {actions ? (
          <div className="flex flex-col gap-2 sm:flex-row">{actions}</div>
        ) : null}
      </CardBody>
    </Card>
  );
}
