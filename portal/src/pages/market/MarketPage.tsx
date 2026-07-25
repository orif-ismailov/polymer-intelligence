import { useMemo, useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useMarket, type MarketFilters, type MarketOffer } from "@/entities/market";
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

function priceLabel(offer: MarketOffer, onRequest: string): string {
  if (offer.price == null) return onRequest;
  return `${offer.price} ${offer.currency}`;
}

function MarketCard({ offer, onOpen }: { offer: MarketOffer; onOpen: () => void }) {
  const { t } = useTranslation();
  const product = offer.grade_text ?? offer.product_text ?? "—";
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-lg"
    >
      <Card className="h-full transition-colors hover:border-accent">
      <CardBody className="space-y-2">
        <div className="flex items-start justify-between gap-2">
          <span className="font-semibold text-text">{product}</span>
          <Badge tone={offer.availability === "in_stock" ? "success" : "neutral"}>
            {t(`availability.${offer.availability}`)}
          </Badge>
        </div>
        <div className="text-sm text-text-muted">
          {t("market.price")}:{" "}
          <span className="font-medium text-text">
            {priceLabel(offer, t("market.onRequest"))}
          </span>
        </div>
        {offer.qty_available != null ? (
          <div className="text-sm text-text-muted">
            {t("market.qty")}: {offer.qty_available} {offer.qty_unit}
          </div>
        ) : null}
        <div className="flex items-center justify-between gap-2 pt-1">
          <span className="truncate text-sm text-text-muted">
            {offer.display_name ?? "—"}
            {offer.country ? ` · ${offer.country}` : ""}
          </span>
          {offer.company_verified ? (
            <Badge tone="success">{t("market.verified")}</Badge>
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

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-48 flex-1">
          <Input
            placeholder={t("market.searchPlaceholder")}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
            aria-label={t("market.searchPlaceholder")}
          />
        </div>
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
          className="w-28"
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
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
