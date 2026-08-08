import { useTranslation } from "react-i18next";

import { type NewsFacet, type NewsFilterOptions } from "@/entities/news";
import { cn } from "@/shared/lib";
import { Skeleton } from "@/shared/ui";

export interface NewsFilterState {
  category: string | null;
  country: string | null;
  product: string | null;
}

interface NewsFiltersProps {
  /**
   * Namespaces every `id` in this instance.
   *
   * Same reason as `MarketFilters`: the desktop rail stays mounted
   * (`hidden lg:block`) while the phone sheet mounts on demand, so both copies
   * are in the document at once whenever the sheet is open. Duplicate ids are
   * invalid and every `htmlFor` would resolve to whichever came first.
   */
  idPrefix: string;
  state: NewsFilterState;
  options: NewsFilterOptions | undefined;
  loading: boolean;
  /** Writes one filter into the query string; `null` clears it. */
  onChange: (key: string, value: string | null) => void;
  className?: string;
}

/**
 * The reader's facet controls, in one definition rendered in two places: the
 * desktop rail and the phone bottom sheet.
 *
 * The facets are *live* — the backend only returns values that appear in recent
 * news, so a control here can never offer a filter that returns nothing. That is
 * why there is no static list of categories or countries anywhere in this file.
 *
 * Every control writes straight to the URL through `onChange` and holds no state
 * of its own, which is what keeps a filtered view linkable and the back button
 * working. It is also why the sheet needs no "apply": by the time it closes, the
 * filters have already been applied.
 *
 * `companies` is served by the same endpoint and the `company` filter works, but
 * it is not surfaced — the facet is long, sparse and mostly one-article values,
 * which makes it a scroll rather than a filter. The Mini App leaves it out for
 * the same reason.
 */
export function NewsFilters({
  idPrefix,
  state,
  options,
  loading,
  onChange,
  className,
}: NewsFiltersProps) {
  const { t } = useTranslation();

  const rowClass =
    "flex min-h-11 w-full items-center justify-between gap-2 rounded-md px-2 text-sm transition-colors lg:min-h-0 lg:py-1.5";

  /**
   * One facet group. Tapping the active value clears it, so the group needs no
   * separate "any" row — but it gets one anyway, because on a list this long the
   * way back to unfiltered should not depend on remembering which row you tapped.
   */
  function group(
    key: string,
    label: string,
    facets: NewsFacet[],
    selected: string | null,
    // Facet display text; country codes and product tickers read fine raw,
    // category slugs do not.
    format: (value: string) => string = (value) => value,
  ) {
    if (!loading && facets.length === 0) return null;
    return (
      <div>
        <span
          id={`${idPrefix}-${key}-label`}
          className="block text-xs font-medium text-text-muted"
        >
          {label}
        </span>
        {loading ? (
          <div className="mt-2 space-y-1.5">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-full" />
          </div>
        ) : (
          <ul className="mt-2 space-y-0.5" aria-labelledby={`${idPrefix}-${key}-label`}>
            <li>
              <button
                type="button"
                onClick={() => onChange(key, null)}
                aria-pressed={selected === null}
                className={cn(
                  rowClass,
                  selected === null
                    ? "bg-brand-soft text-brand"
                    : "text-text-muted hover:bg-surface-2 hover:text-text",
                )}
              >
                {t("news.filterAny")}
              </button>
            </li>
            {facets.map((f) => (
              <li key={f.value}>
                <button
                  type="button"
                  onClick={() => onChange(key, selected === f.value ? null : f.value)}
                  aria-pressed={selected === f.value}
                  className={cn(
                    rowClass,
                    selected === f.value
                      ? "bg-brand-soft text-brand"
                      : "text-text-muted hover:bg-surface-2 hover:text-text",
                  )}
                >
                  <span className="truncate">{format(f.value)}</span>
                  <span className="num shrink-0 text-xs text-text-subtle">{f.count}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  return (
    <div className={cn("space-y-6", className)}>
      {group("category", t("news.filterCategory"), options?.categories ?? [], state.category, (v) =>
        t(`news.category.${v}`, v),
      )}
      {group("country", t("news.filterCountry"), options?.countries ?? [], state.country)}
      {group("product", t("news.relatedProducts"), options?.products ?? [], state.product)}
    </div>
  );
}
