import { useTranslation } from "react-i18next";

import { LabBadges } from "@/entities/lab";
import type { MarketOfferDetail, OfferFileRef } from "@/entities/market";
import { coerceLang } from "@/shared/i18n";
import { countryName, formatMoney } from "@/shared/lib";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CheckCircleIcon,
  HeartIcon,
  SendIcon,
} from "@/shared/ui";

import { OfferGallery } from "./OfferGallery";

interface OfferHeroProps {
  offer: MarketOfferDetail;
  photos: OfferFileRef[];
  onPhotoChange?: (index: number) => void;
  onRequestRfq: () => void;
  onToggleFavorite: () => void;
  canInquire: boolean;
}

/**
 * The product-detail hero (`docs/new-design/product_detail.jpeg`): swipeable
 * gallery, title / price / badges, and the two full-width CTAs under the strip
 * (not squeezed into the narrow side column).
 */
export function OfferHero({
  offer,
  photos,
  onPhotoChange,
  onRequestRfq,
  onToggleFavorite,
  canInquire,
}: OfferHeroProps) {
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
            into the half-width info column beside the gallery. */}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Button
            size="lg"
            fullWidth
            disabled={!canInquire || !offer.accepts_rfq}
            onClick={onRequestRfq}
            data-testid="product-detail-rfq"
          >
            <SendIcon size={16} />
            {t("market.detail.requestRfq")}
          </Button>
          <Button
            size="lg"
            variant="outline"
            fullWidth
            aria-pressed={offer.is_favorite}
            onClick={onToggleFavorite}
            data-testid="product-detail-favorite"
          >
            <HeartIcon size={16} className={offer.is_favorite ? "text-danger" : undefined} />
            {t(offer.is_favorite ? "market.unfavorite" : "market.detail.addFavorite")}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
