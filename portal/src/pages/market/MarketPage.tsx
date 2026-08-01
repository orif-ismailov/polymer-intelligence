import { useMemo, useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { MarketOfferCard, useMarket, type MarketFilters } from "@/entities/market";
import { AVAILABILITY } from "@/shared/config";
import {
  Button,
  EmptyState,
  ErrorView,
  Input,
  PageHeader,
  Skeleton,
  tabItemClasses,
  Tabs,
  type TabItem,
  StoreIcon,
} from "@/shared/ui";

const PAGE_SIZE = 24;

export function MarketPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  // Deep link from a seller profile's «Смотреть все». Two spellings because two
  // profile sheets emit it: the cabinet's own uses `?seller`, the shared public
  // company page uses the API's `?seller_company_id` and is mounted in BOTH
  // tiers, so its link reaches this page as `/cabinet/market?seller_company_id=`.
  const sellerRaw = searchParams.get("seller") ?? searchParams.get("seller_company_id");
  const sellerCompanyId =
    sellerRaw && /^\d+$/.test(sellerRaw) ? Number(sellerRaw) : undefined;

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
      seller_company_id: sellerCompanyId,
    }),
    [q, availability, country, hasPassport, labVerified, sellerCompanyId],
  );

  const marketQuery = useMarket(filters, companyId, offset);
  const offers = marketQuery.data ?? [];

  const availabilityTabs: TabItem[] = [
    { id: "", label: t("market.availabilityAll") },
    ...AVAILABILITY.map((a) => ({ id: a, label: t(`availability.${a}`) })),
  ];

  return (
    <div className="space-y-5">
      <PageHeader title={t("market.title")} subtitle={t("market.subtitle")} />

      {/* Search takes the row; the country code sits beside it once there's width. */}
      <div className="grid gap-3 sm:grid-cols-[1fr_7rem]">
        <Input
          placeholder={t("market.searchPlaceholder")}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
          aria-label={t("market.searchPlaceholder")}
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

      {/*
       * The sheet filters with chips, not a select and two checkboxes: they read
       * as one row of the same control, and the applied filters stay visible
       * instead of collapsing into a closed dropdown. Same state, same query.
       *
       * Two laboratory filters, not one: "there is an analysis" and "we arranged
       * it" are different levels of trust, and FR-L5 asks for both. They toggle
       * independently, so they are their own chips rather than a third tab.
       */}
      <div className="flex flex-wrap items-center gap-2">
        <Tabs
          variant="pill"
          items={availabilityTabs}
          value={availability}
          onChange={(id) => {
            setAvailability(id);
            setOffset(0);
          }}
          label={t("market.availability")}
        />
        <button
          type="button"
          aria-pressed={hasPassport}
          onClick={() => {
            setHasPassport((v) => !v);
            setOffset(0);
          }}
          className={tabItemClasses("pill", hasPassport)}
        >
          {t("market.filter.labPassport")}
        </button>
        <button
          type="button"
          aria-pressed={labVerified}
          onClick={() => {
            setLabVerified((v) => !v);
            setOffset(0);
          }}
          className={tabItemClasses("pill", labVerified)}
        >
          {t("market.filter.labVerified")}
        </button>
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
                onOpen={() => navigate(`/cabinet/market/${offer.id}`)}
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
        <EmptyState icon={<StoreIcon size={28} />} title={t("market.empty")} description={t("market.emptyBody")} />
      )}
    </div>
  );
}
