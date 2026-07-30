import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { MarketOfferCard, useFavorites } from "@/entities/market";
import {
  EmptyState,
  ErrorView,
  LinkButton,
  PageHeader,
  Skeleton,
  HeartIcon,
} from "@/shared/ui";

/**
 * The account's shortlist.
 *
 * Deliberately not company-scoped: a bookmark is personal, so switching company
 * hats in the topbar does not change what is listed here. Only offers that are
 * still on sale come back — an archived one would be a card a buyer cannot act
 * on.
 *
 * Renders the SAME card as the market grid. It briefly had its own copy, and the
 * two drifted within a commit: the shortlist lost the role badges and the seller
 * line, so an offer looked different depending on which list you opened it from.
 */
export function FavoritesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const query = useFavorites();

  if (query.isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
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

  return (
    <div className="space-y-5">
      <PageHeader title={t("market.favorites")} subtitle={t("market.favoritesHint")} />

      {items.length === 0 ? (
        <EmptyState
          icon={<HeartIcon size={28} />}
          title={t("market.favoritesEmpty")}
          description={t("market.favoritesEmptyBody")}
          action={<LinkButton to="/market">{t("market.title")}</LinkButton>}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((offer) => (
            <MarketOfferCard
              key={offer.id}
              offer={offer}
              onOpen={() => navigate(`/market/${offer.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
