import { useMemo, useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { MarketOfferCard, useMarket, type MarketFilters } from "@/entities/market";
import { AVAILABILITY } from "@/shared/config";
import {
  Button,
  Checkbox,
  EmptyState,
  ErrorView,
  Input,
  Select,
  Skeleton,
} from "@/shared/ui";

const PAGE_SIZE = 24;

export function MarketPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const [q, setQ] = useState("");
  const [availability, setAvailability] = useState("");
  const [country, setCountry] = useState("");
  const [hasPassport, setHasPassport] = useState(false);
  const [labVerified, setLabVerified] = useState(false);
  const [offset, setOffset] = useState(0);

  const filters: MarketFilters = useMemo(
    () => ({
      q: q.trim() || undefined,
      availability: availability ? (availability as MarketFilters["availability"]) : undefined,
      country: country.trim().toUpperCase() || undefined,
      has_lab_passport: hasPassport || undefined,
      lab_verified: labVerified || undefined,
    }),
    [q, availability, country, hasPassport, labVerified],
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

      {/* Two laboratory filters, not one: "there is an analysis" and "we
          arranged it" are different levels of trust, and FR-L5 asks for both. */}
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        <Checkbox
          checked={hasPassport}
          onChange={(e) => {
            setHasPassport(e.target.checked);
            setOffset(0);
          }}
          label={t("market.filter.labPassport")}
        />
        <Checkbox
          checked={labVerified}
          onChange={(e) => {
            setLabVerified(e.target.checked);
            setOffset(0);
          }}
          label={t("market.filter.labVerified")}
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
              <MarketOfferCard
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
