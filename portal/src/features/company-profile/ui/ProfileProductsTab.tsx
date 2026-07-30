import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import type { MarketOffer } from "@/entities/market";
import { offerImageUrl, offerPhotos } from "@/entities/market";
import {
  Badge,
  CheckCircleIcon,
  ChevronRightIcon,
  EmptyState,
  ImageIcon,
  PackageOpenIcon,
} from "@/shared/ui";

interface ProfileProductsTabProps {
  offers: MarketOffer[];
  offerCount: number;
  onSeeAll?: () => void;
}

/**
 * «Продукты» — vertical list matching the mockup: thumb · name · CAS · stock · chevron.
 */
export function ProfileProductsTab({ offers, offerCount, onSeeAll }: ProfileProductsTabProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

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
          const cover = offerPhotos(offer.files)[0] ?? null;
          return (
            <button
              key={offer.id}
              type="button"
              onClick={() => navigate(`/market/${offer.id}`)}
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
            </button>
          );
        })}
      </div>
      {offerCount > offers.length && onSeeAll ? (
        <button
          type="button"
          onClick={onSeeAll}
          className="w-full rounded-md border border-border px-3 py-2.5 text-sm font-medium text-brand transition-colors hover:border-brand-line hover:bg-brand-soft"
        >
          {t("companyProfile.seeAllProducts", { count: offerCount })}
        </button>
      ) : null}
    </div>
  );
}
