import { useMemo, useState, type FormEvent } from "react";

import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { usePublicCategories, usePublicStats, type PublicFacet } from "@/entities/public";
import { Skeleton, buttonClasses } from "@/shared/ui";

const FALLBACK_CATEGORIES = [
  { code: "PE", q: "PE" },
  { code: "PP", q: "PP" },
  { code: "PVC", q: "PVC" },
  { code: "PET", q: "PET" },
  { code: "PS", q: "PS" },
  { code: "Rubber", q: "Каучук" },
  { code: "Solvents", q: "Растворители" },
  { code: "Additives", q: "Добавки" },
] as const;

const AVAILABILITY_VALUES = ["in_stock", "on_order"] as const;

/**
 * Left column of the marketplace body (marketplace.jpeg §4): product categories
 * over a filter form that lands on `/market` with the same query-string contract.
 *
 * The mockup's four dropdowns are Страна происхождения / Форма поставки /
 * Условия поставки / Производитель. Three map onto real catalog filters; the
 * second does NOT — there is no "delivery form" field anywhere in the schema —
 * so that slot carries the real `availability` filter under an honest label
 * rather than a control that does nothing.
 *
 * Options come from `/public/stats` (`countries` / `incoterms` / `companies`),
 * aggregated from approved offers, so a dropdown can never offer a value that
 * matches nothing. Categories drop their counts here: the mockup shows none, and
 * the count is still on `/market`.
 */
export function CatalogSidebar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const categories = usePublicCategories();
  const stats = usePublicStats();
  const [country, setCountry] = useState("");
  const [availability, setAvailability] = useState("");
  const [incoterms, setIncoterms] = useState("");
  const [company, setCompany] = useState("");

  const list = useMemo(() => {
    const api = categories.data ?? [];
    if (api.length > 0)
      return api.slice(0, 9).map((c) => ({
        key: String(c.product_id),
        label: c.label,
        to: `/market?product_id=${c.product_id}`,
      }));
    return FALLBACK_CATEGORIES.map((c) => ({
      key: c.code,
      label: t(`public.home.fallbackCategory.${c.code}`, { defaultValue: c.code }),
      to: `/market?q=${encodeURIComponent(c.q)}`,
    }));
  }, [categories.data, t]);

  function onSubmit(e: FormEvent): void {
    e.preventDefault();
    const params = new URLSearchParams();
    if (country) params.set("country", country);
    if (availability) params.set("availability", availability);
    if (incoterms) params.set("incoterms", incoterms);
    if (company) params.set("seller_company_id", company);
    const qs = params.toString();
    void navigate(qs ? `/market?${qs}` : "/market");
  }

  function resetFilters(): void {
    setCountry("");
    setAvailability("");
    setIncoterms("");
    setCompany("");
  }

  const total = stats.data?.offer_count ?? 0;

  return (
    <aside className="space-y-3">
      <section
        aria-labelledby="home-categories"
        className="rounded-md border border-border bg-surface p-4"
      >
        <h3 id="home-categories" className="text-sm font-semibold text-text">
          {t("public.home.productCategories")}
        </h3>
        {categories.isLoading ? (
          <div className="mt-3 space-y-2">
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
          </div>
        ) : (
          <ul className="mt-2.5">
            {list.map((item) => (
              <li key={item.key}>
                <Link
                  to={item.to}
                  className="flex items-center gap-2 rounded-sm px-1 py-[0.3125rem] text-[12px] text-text-muted transition-colors hover:bg-surface-2 hover:text-text"
                >
                  <ChevronRight
                    size={12}
                    strokeWidth={2}
                    aria-hidden
                    className="shrink-0 text-text-subtle"
                  />
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <Link
          to="/market"
          className="mt-3 flex h-9 items-center justify-center rounded-sm border border-border-strong text-[12px] font-medium text-text transition-colors hover:border-brand-line hover:bg-brand-soft hover:text-brand"
        >
          {t("public.market.allCategories")}
        </Link>
      </section>

      <section
        aria-labelledby="home-filters"
        className="rounded-md border border-border bg-surface p-4"
      >
        <div className="flex items-baseline justify-between gap-2">
          <h3 id="home-filters" className="text-sm font-semibold text-text">
            {t("public.market.filters")}
          </h3>
          <button
            type="button"
            onClick={resetFilters}
            className="text-[11px] font-medium text-brand underline underline-offset-2"
          >
            {t("public.home.resetFilters")}
          </button>
        </div>

        <form onSubmit={onSubmit} className="mt-3.5 space-y-3">
          <FilterSelect
            id="home-filter-country"
            label={t("public.home.filterCountry")}
            placeholder={t("public.home.filterCountryPlaceholder")}
            value={country}
            onChange={setCountry}
            options={stats.data?.countries ?? []}
          />

          <FilterSelect
            id="home-filter-availability"
            label={t("public.market.availability")}
            placeholder={t("public.market.any")}
            value={availability}
            onChange={setAvailability}
            options={AVAILABILITY_VALUES.map((v) => ({
              value: v,
              label: t(`availability.${v}`),
              offer_count: 0,
            }))}
          />

          <FilterSelect
            id="home-filter-incoterms"
            label={t("public.home.filterIncoterms")}
            placeholder={t("public.market.anyPlural")}
            value={incoterms}
            onChange={setIncoterms}
            options={stats.data?.incoterms ?? []}
          />

          <FilterSelect
            id="home-filter-company"
            label={t("public.home.filterCompany")}
            placeholder={t("public.home.filterCompanyPlaceholder")}
            value={company}
            onChange={setCompany}
            options={stats.data?.companies ?? []}
          />

          <button
            type="submit"
            className={buttonClasses({ fullWidth: true, className: "!h-10 !text-[13px]" })}
          >
            {stats.isLoading
              ? t("public.home.showProducts")
              : t("public.home.showProductsCount", { count: total })}
          </button>
        </form>
      </section>
    </aside>
  );
}

interface FilterSelectProps {
  id: string;
  label: string;
  placeholder: string;
  value: string;
  onChange: (next: string) => void;
  options: readonly PublicFacet[];
}

/**
 * One labelled dropdown of the mockup's filter stack. Local rather than
 * `shared/ui`'s `Select` because that primitive is `h-10 text-sm` for cabinet
 * forms, and the storefront sidebar is a denser 34px/12px well.
 */
function FilterSelect({ id, label, placeholder, value, onChange, options }: FilterSelectProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-[11px] text-text-muted">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={options.length === 0}
        className="h-[2.125rem] w-full rounded-sm border border-border bg-surface-inset px-2.5 text-[12px] text-text transition-colors focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:text-text-subtle"
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
