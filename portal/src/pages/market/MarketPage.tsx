import { useMemo, useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import {
  FavoriteButton,
  OfferReadinessBadges,
  offerImageUrl,
  offerPhotos,
  useMarket,
  type MarketFilters,
  type MarketOffer,
} from "@/entities/market";
import { AVAILABILITY } from "@/shared/config";
import {
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  Input,
  Select,
  Skeleton,
} from "@/shared/ui";

const PAGE_SIZE = 24;

function MarketCard({ offer, onOpen }: { offer: MarketOffer; onOpen: () => void }) {
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
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M3.5 6.5h17v11h-17zM3.5 15l4.5-4 3.5 3 3-2.5 6 5"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  strokeLinejoin="round"
                />
                <circle cx="9" cy="10" r="1.3" fill="currentColor" />
              </svg>
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

          <OfferReadinessBadges offer={offer} />

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

export function MarketPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const [q, setQ] = useState("");
  const [availability, setAvailability] = useState("");
  const [country, setCountry] = useState("");
  const [offset, setOffset] = useState(0);

  const filters: MarketFilters = useMemo(
    () => ({
      q: q.trim() || undefined,
      availability: availability ? (availability as MarketFilters["availability"]) : undefined,
      country: country.trim().toUpperCase() || undefined,
    }),
    [q, availability, country],
  );

  const marketQuery = useMarket(filters, companyId, offset);
  const offers = marketQuery.data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-text">{t("market.title")}</h1>
        <p className="mt-1 text-sm text-text-muted">{t("market.subtitle")}</p>
      </div>

      {/* Search takes the row; the two filters sit beside it once there's width. */}
      <div className="grid gap-3 sm:grid-cols-[1fr_11rem_7rem]">
        <Input
          placeholder={t("market.searchPlaceholder")}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
          aria-label={t("market.searchPlaceholder")}
        />
        <Select
          value={availability}
          onChange={(e) => {
            setAvailability(e.target.value);
            setOffset(0);
          }}
          aria-label={t("market.availability")}
          options={[
            { value: "", label: t("market.availabilityAll") },
            ...AVAILABILITY.map((a) => ({ value: a, label: t(`availability.${a}`) })),
          ]}
        />
        <Input
          placeholder={t("market.country")}
          value={country}
          onChange={(e) => {
            setCountry(e.target.value);
            setOffset(0);
          }}
          aria-label={t("market.country")}
          maxLength={2}
        />
      </div>

      {marketQuery.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : marketQuery.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void marketQuery.refetch()}
        />
      ) : offers.length > 0 ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {offers.map((offer) => (
              <MarketCard
                key={offer.id}
                offer={offer}
                onOpen={() => navigate(`/market/${offer.id}`)}
              />
            ))}
          </div>
          <div className="flex items-center justify-between">
            <Button
              variant="secondary"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            >
              {t("common.prev")}
            </Button>
            <Button
              variant="secondary"
              disabled={offers.length < PAGE_SIZE}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
            >
              {t("common.next")}
            </Button>
          </div>
        </>
      ) : (
        <EmptyState title={t("market.empty")} description={t("market.emptyBody")} />
      )}
    </div>
  );
}
