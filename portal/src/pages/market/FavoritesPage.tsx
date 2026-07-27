import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  FavoriteButton,
  OfferReadinessBadges,
  offerImageUrl,
  offerPhotos,
  useFavorites,
} from "@/entities/market";
import {
  Badge,
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  LinkButton,
  Skeleton,
} from "@/shared/ui";

/**
 * The account's shortlist.
 *
 * Deliberately not company-scoped: a bookmark is personal, so switching company
 * hats in the topbar does not change what is listed here. Only offers that are
 * still on sale come back — an archived one would be a card a buyer cannot act
 * on.
 */
export function FavoritesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const query = useFavorites();

  if (query.isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-64 w-full" />
        ))}
      </div>
    );
  }

  if (query.isError) {
    return (
      <ErrorView
        title={t("errors.loadFailed")}
        retryLabel={t("common.retry")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const items = query.data ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        title={t("market.favoritesEmpty")}
        description={t("market.favoritesEmptyBody")}
        action={<LinkButton to="/market">{t("market.title")}</LinkButton>}
      />
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-text">{t("market.favorites")}</h1>
        <p className="mt-1 text-sm text-text-muted">{t("market.favoritesHint")}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((offer) => {
          const cover = offerPhotos(offer.files)[0] ?? null;
          const title = offer.product_text ?? offer.grade_text ?? "—";
          return (
            <button
              key={offer.id}
              type="button"
              onClick={() => navigate(`/market/${offer.id}`)}
              className="w-full rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <Card className="flex h-full flex-col overflow-hidden transition-colors hover:border-brand-line">
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
                  ) : null}
                </div>
                <CardBody className="flex flex-1 flex-col gap-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="min-w-0 truncate font-semibold text-text">{title}</p>
                    <Badge variant={offer.availability === "in_stock" ? "in-stock" : "on-order"}>
                      {t(`availability.${offer.availability}`)}
                    </Badge>
                  </div>
                  {offer.price == null ? (
                    <p className="text-lg font-semibold text-text-muted">
                      {t("market.onRequest")}
                    </p>
                  ) : (
                    <p className="num text-lg font-semibold leading-tight text-brand">
                      {offer.price}{" "}
                      <span className="text-sm font-medium text-text-muted">
                        {offer.currency}
                        {offer.qty_unit ? `/${offer.qty_unit}` : ""}
                      </span>
                    </p>
                  )}
                  <OfferReadinessBadges offer={offer} className="mt-auto" />
                </CardBody>
              </Card>
            </button>
          );
        })}
      </div>
    </div>
  );
}
