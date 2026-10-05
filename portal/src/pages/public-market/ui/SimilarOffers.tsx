import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { PublicOfferTile, useSimilarOffers, type PublicOfferDetail } from "@/entities/public";
import { SectionHeader } from "@/features/product-detail";

/**
 * «Похожие предложения» — the last block on an offer page: the same catalog
 * product first, then the same category (the backend decides the order).
 *
 * Renders nothing until there is something to show. An empty heading, or a
 * skeleton for a row that often turns out to be empty, would end the page on a
 * promise it does not keep.
 */
export function SimilarOffers({ offer }: { offer: PublicOfferDetail }) {
  const { t } = useTranslation();
  const similar = useSimilarOffers(offer.id);
  const items = similar.data ?? [];
  if (items.length === 0) return null;

  return (
    <section data-testid="product-detail-similar" className="pt-2">
      <SectionHeader
        title={t("public.offer.similarTitle")}
        action={
          offer.product_id != null ? (
            <Link
              to={`/market?product_id=${offer.product_id}`}
              className="shrink-0 text-sm text-brand hover:underline"
            >
              {t("public.offer.similarSeeAll")}
            </Link>
          ) : null
        }
      />
      <ul className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        {items.map((item) => (
          <li key={item.id} data-testid="similar-offer-tile" className="min-w-0">
            <PublicOfferTile offer={item} />
          </li>
        ))}
      </ul>
    </section>
  );
}
