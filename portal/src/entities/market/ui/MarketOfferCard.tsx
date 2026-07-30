import { useTranslation } from "react-i18next";

import { LabBadges } from "@/entities/lab";
import {
  Badge,
  Card,
  CardBody,
  ImageIcon,
} from "@/shared/ui";

import { offerImageUrl, offerPhotos } from "../model/api";
import type { MarketOffer } from "../model/types";
import { BusinessRoleBadges } from "./BusinessRoleBadges";
import { FavoriteButton } from "./FavoriteButton";
import { OfferReadinessBadges } from "./OfferReadinessBadges";

interface MarketOfferCardProps {
  offer: MarketOffer;
  onOpen: () => void;
}

/**
 * The market offer card.
 *
 * Lives here rather than in a page because BOTH the market grid and the
 * favourites list render it. They were duplicated markup for one commit, and the
 * copies immediately drifted — the shortlist lost its role badges and the seller
 * line, so the same offer looked like a different offer depending on which list
 * you opened it from.
 */
export function MarketOfferCard({ offer, onOpen }: MarketOfferCardProps) {
  const { t } = useTranslation();
  // Mockup hierarchy: the product name is the headline, the grade its subtitle.
  const title = offer.product_text ?? offer.grade_text ?? "—";
  const subtitle = offer.product_text && offer.grade_text ? offer.grade_text : null;
  const location = [offer.warehouse_city, offer.country].filter(Boolean).join(", ");
  const cover = offerPhotos(offer.files)[0] ?? null;

  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
    >
      <Card className="flex h-full flex-col overflow-hidden transition-colors hover:border-brand-line">
        {/* Cover photo, or a neutral placeholder so a photo-less offer doesn't
            collapse the card and break the grid (FR-M3). */}
        <div className="relative aspect-[4/3] w-full border-b border-border bg-surface-inset">
          <FavoriteButton
            offerId={offer.id}
            isFavorite={offer.is_favorite}
            className="absolute right-2 top-2 z-10"
          />
          {cover ? (
            <img
              src={offerImageUrl(offer.id, cover.id)}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-text-subtle">
              <ImageIcon size={28} />
            </div>
          )}
        </div>
        <CardBody className="flex flex-1 flex-col gap-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-semibold text-text">{title}</p>
              {subtitle ? (
                <p className="truncate text-xs text-text-muted">{subtitle}</p>
              ) : null}
            </div>
            <Badge variant={offer.availability === "in_stock" ? "in-stock" : "on-order"}>
              {t(`availability.${offer.availability}`)}
            </Badge>
          </div>

          {/* The price is the card's focal point in the mockups. */}
          <div>
            {offer.price == null ? (
              <p className="text-lg font-semibold text-text-muted">{t("market.onRequest")}</p>
            ) : (
              <p className="num text-lg font-semibold leading-tight text-brand">
                {offer.price}{" "}
                <span className="text-sm font-medium text-text-muted">
                  {offer.currency}
                  {offer.qty_unit ? `/${offer.qty_unit}` : ""}
                </span>
              </p>
            )}
            {offer.qty_available != null ? (
              <p className="num mt-0.5 text-xs text-text-muted">
                {t("market.qty")}: {offer.qty_available} {offer.qty_unit}
              </p>
            ) : null}
            {/* For a made-to-order offer this is the only number a buyer can plan
                around — the price is "on request". */}
            {offer.lead_time_days != null ? (
              <p className="num mt-0.5 text-xs text-text-muted">
                {t("market.leadTime", { count: offer.lead_time_days })}
              </p>
            ) : null}
          </div>

          {/* Three badge rows, and they say different things: what the SELLER is
              (confirmed roles), what they are ready to DO, and what has been
              checked about the MATERIAL. */}
          <BusinessRoleBadges roles={offer.business_roles} max={2} />
          <OfferReadinessBadges offer={offer} />
          <LabBadges
            hasLabPassport={offer.has_lab_passport}
            labVerified={offer.lab_verified}
          />

          <div className="mt-auto flex items-end justify-between gap-2 border-t border-border pt-3">
            <span className="min-w-0 text-sm text-text-muted">
              <span className="block truncate">{offer.display_name ?? "—"}</span>
              {location ? (
                <span className="block truncate text-xs text-text-subtle">{location}</span>
              ) : null}
            </span>
            {offer.company_verified ? (
              <Badge variant="verified" className="shrink-0">
                {t("market.verified")}
              </Badge>
            ) : null}
          </div>
        </CardBody>
      </Card>
    </button>
  );
}
