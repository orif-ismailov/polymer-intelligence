import { useTranslation } from "react-i18next";
import { Pagination } from "swiper/modules";
import { Swiper, SwiperSlide } from "swiper/react";

import type { OfferFileRef } from "@/entities/market";
import { offerImageUrl } from "@/entities/market";
import { Badge, ImageIcon } from "@/shared/ui";

import "swiper/css";
import "swiper/css/pagination";

interface OfferGalleryProps {
  offerId: number;
  photos: OfferFileRef[];
  labVerified: boolean;
  onActiveIndexChange?: (index: number) => void;
}

/**
 * Product-detail photo strip — swipeable Swiper with bullet pagination
 * (https://swiperjs.com/react). Replaces the old static image + non-swipe dots.
 */
export function OfferGallery({
  offerId,
  photos,
  labVerified,
  onActiveIndexChange,
}: OfferGalleryProps) {
  const { t } = useTranslation();

  if (photos.length === 0) {
    return (
      <div
        className="relative overflow-hidden rounded-md border border-border bg-surface-inset"
        data-testid="product-detail-gallery"
      >
        <div className="flex aspect-square w-full flex-col items-center justify-center gap-2 text-text-subtle">
          <ImageIcon size={28} />
          <span className="text-xs">{t("market.detail.noPhoto")}</span>
        </div>
        {labVerified ? (
          <span className="absolute left-2 top-2">
            <Badge variant="lab-verified">{t("lab.badge.verified")}</Badge>
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <div
      className="relative overflow-hidden rounded-md border border-border bg-surface-inset"
      data-testid="product-detail-gallery"
    >
      <Swiper
        modules={[Pagination]}
        slidesPerView={1}
        spaceBetween={0}
        speed={350}
        grabCursor
        pagination={photos.length > 1 ? { clickable: true } : false}
        onSlideChange={(swiper) => onActiveIndexChange?.(swiper.activeIndex)}
        className="product-detail-swiper aspect-square w-full"
        aria-label={t("market.detail.gallery")}
      >
        {photos.map((photo) => (
          <SwiperSlide key={photo.id} className="!h-full">
            <img
              src={offerImageUrl(offerId, photo.id)}
              alt={photo.file_name}
              className="h-full w-full object-cover"
              draggable={false}
            />
          </SwiperSlide>
        ))}
      </Swiper>

      {labVerified ? (
        <span className="pointer-events-none absolute left-2 top-2 z-10">
          <Badge variant="lab-verified">{t("lab.badge.verified")}</Badge>
        </span>
      ) : null}
    </div>
  );
}
