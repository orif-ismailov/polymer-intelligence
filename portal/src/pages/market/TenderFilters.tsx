import { useTranslation } from "react-i18next";

import type { OpenRfqFilters } from "@/entities/deal";
import { productName, useProducts } from "@/entities/product";
import { Button, Select, Tabs, tabItemClasses, type TabItem } from "@/shared/ui";

import { QUOTE_STATUSES, type QuoteStatus } from "./quoteStatus";

/**
 * The filter bars of «Открытые тендеры», one per tab.
 *
 * Neither holds state: every control writes straight to the URL through the
 * page, so a filtered view is a link. The page writes with `replace`, so toggling
 * filters does not pile up history entries between the supplier and «Назад».
 */

type ToggleKey = "closingSoon" | "urgent" | "unanswered";
const TOGGLES: readonly ToggleKey[] = ["closingSoon", "urgent", "unanswered"];

interface OpenTenderFiltersProps {
  filters: OpenRfqFilters;
  onProductChange: (productId: number | null) => void;
  onToggle: (key: ToggleKey, on: boolean) => void;
  onReset: () => void;
}

export function OpenTenderFilters({
  filters,
  onProductChange,
  onToggle,
  onReset,
}: OpenTenderFiltersProps) {
  const { t, i18n } = useTranslation();
  const products = useProducts();
  const productOptions = [
    { value: "", label: t("rfq.filters.allProducts") },
    ...(products.data ?? [])
      .filter((product) => product.is_active)
      // Code first («HDPE · Полиэтилен высокой плотности»): the closed select
      // clips a long name, and the code is what a supplier scans for.
      .map((product) => ({
        value: String(product.id),
        label: `${product.code} · ${productName(product, i18n.language)}`,
      })),
  ];
  const active = filters.productId != null || TOGGLES.some((key) => filters[key]);

  return (
    <div
      role="group"
      aria-label={t("rfq.filters.label")}
      className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center"
    >
      <div className="md:w-80">
        <Select
          aria-label={t("rfq.filters.product")}
          options={productOptions}
          value={filters.productId != null ? String(filters.productId) : ""}
          onChange={(e) => onProductChange(e.target.value ? Number(e.target.value) : null)}
        />
      </div>
      {/* Independent on/off switches, so toggle buttons wearing the pill-chip
          look — not `Tabs`, which picks exactly one. */}
      <div className="flex flex-wrap items-center gap-2">
        {TOGGLES.map((key) => {
          const on = Boolean(filters[key]);
          return (
            <button
              key={key}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(key, !on)}
              className={tabItemClasses("pill", on)}
            >
              {t(`rfq.filters.${key}`)}
            </button>
          );
        })}
      </div>
      {active ? (
        <Button variant="ghost" size="sm" onClick={onReset} className="self-start md:ms-auto md:self-auto">
          {t("rfq.filters.reset")}
        </Button>
      ) : null}
    </div>
  );
}

interface QuoteStatusFilterProps {
  status: QuoteStatus | null;
  onChange: (status: QuoteStatus | null) => void;
}

export function QuoteStatusFilter({ status, onChange }: QuoteStatusFilterProps) {
  const { t } = useTranslation();
  const items: TabItem[] = [
    { id: "", label: t("rfq.filters.allStatuses") },
    ...QUOTE_STATUSES.map((value) => ({ id: value, label: t(`rfq.status.${value}`) })),
  ];
  return (
    <Tabs
      variant="pill"
      items={items}
      value={status ?? ""}
      onChange={(id) => onChange(id ? (id as QuoteStatus) : null)}
      label={t("rfq.filters.status")}
    />
  );
}

