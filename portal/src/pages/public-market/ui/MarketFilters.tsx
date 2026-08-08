import { useTranslation } from "react-i18next";

import { type PublicCategory } from "@/entities/public";
import { cn, useSyncedDraft } from "@/shared/lib";
import { Skeleton } from "@/shared/ui";

export interface MarketFilterState {
  q: string;
  productId: string | null;
  availability: string;
  country: string;
  labVerified: boolean;
  hasPassport: boolean;
}

interface MarketFiltersProps {
  /**
   * Namespaces every `id` in this instance.
   *
   * The desktop rail stays mounted (`hidden lg:block`) while the phone sheet
   * mounts on demand, so while the sheet is open BOTH copies are in the
   * document. Without a prefix they would both claim `market-q`,
   * `market-availability` and `market-country` — duplicate ids are invalid, and
   * every `<label htmlFor>` would resolve to whichever came first, so tapping a
   * label in the sheet would focus a control in the hidden rail.
   *
   * Rendering only one copy would be the other fix, but choosing which needs
   * the viewport, and this page is server-rendered: a `useMediaQuery` deciding
   * what to mount makes the server emit markup the client immediately
   * contradicts.
   */
  idPrefix: string;
  state: MarketFilterState;
  categories: PublicCategory[];
  categoriesLoading: boolean;
  /** Writes one filter into the query string; `null` clears it. */
  onChange: (key: string, value: string | null) => void;
  /** Omits the search field — the phone sheet has it in the sticky bar above. */
  hideSearch?: boolean;
  className?: string;
}

/**
 * The catalog's filter controls, in one definition rendered in two places: the
 * desktop rail and the phone bottom sheet.
 *
 * Every control writes straight to the URL through `onChange` rather than
 * holding local state, which is what keeps a filtered view linkable and the
 * back button working — see the note at the top of `PublicMarketPage`. That is
 * also why the sheet needs no "apply": by the time it closes, the filters have
 * already been applied.
 */
export function MarketFilters({
  idPrefix,
  state,
  categories,
  categoriesLoading,
  onChange,
  hideSearch = false,
  className,
}: MarketFiltersProps) {
  const { t } = useTranslation();
  const id = (name: string): string => `${idPrefix}-${name}`;

  // Drafts re-sync when the URL changes underneath the inputs («Сбросить
  // фильтры», back/forward) — a bare `defaultValue` kept showing the stale
  // text, and the next blur silently re-applied it.
  const [qDraft, setQDraft] = useSyncedDraft(state.q);
  const [countryDraft, setCountryDraft] = useSyncedDraft(state.country);

  // 44px rows throughout. These measured 32px in the rail, which is fine under a
  // mouse and under the touch floor on the surface they now live on.
  const rowClass =
    "flex min-h-11 w-full items-center justify-between gap-2 rounded-md px-2 text-sm transition-colors lg:min-h-0 lg:py-1.5";
  const fieldClass =
    "mt-1.5 h-11 w-full rounded-md border border-border bg-surface-inset px-3 text-sm text-text placeholder:text-text-subtle focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand lg:h-10";

  return (
    <div className={cn("space-y-6", className)}>
      {hideSearch ? null : (
        <div>
          <label htmlFor={id("q")} className="block text-xs font-medium text-text-muted">
            {t("public.market.search")}
          </label>
          <input
            id={id("q")}
            type="search"
            value={qDraft}
            onChange={(e) => setQDraft(e.target.value)}
            onBlur={(e) => onChange("q", e.target.value.trim() || null)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                onChange("q", (e.target as HTMLInputElement).value.trim() || null);
              }
            }}
            placeholder={t("public.market.searchPlaceholder")}
            className={fieldClass}
          />
        </div>
      )}

      <div>
        <span className="block text-xs font-medium text-text-muted">
          {t("public.market.category")}
        </span>
        {categoriesLoading ? (
          <div className="mt-2 space-y-1.5">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-full" />
          </div>
        ) : (
          <ul className="mt-2 space-y-0.5">
            <li>
              <button
                type="button"
                onClick={() => onChange("product_id", null)}
                className={cn(
                  rowClass,
                  !state.productId
                    ? "bg-brand-soft text-brand"
                    : "text-text-muted hover:bg-surface-2 hover:text-text",
                )}
              >
                {t("public.market.allCategories")}
              </button>
            </li>
            {categories.map((cat) => (
              <li key={cat.product_id}>
                <button
                  type="button"
                  onClick={() => onChange("product_id", String(cat.product_id))}
                  className={cn(
                    rowClass,
                    state.productId === String(cat.product_id)
                      ? "bg-brand-soft text-brand"
                      : "text-text-muted hover:bg-surface-2 hover:text-text",
                  )}
                >
                  <span className="truncate">{cat.label}</span>
                  <span className="num shrink-0 text-xs text-text-subtle">{cat.offer_count}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <label
          htmlFor={id("availability")}
          className="block text-xs font-medium text-text-muted"
        >
          {t("public.market.availability")}
        </label>
        <select
          id={id("availability")}
          value={state.availability}
          onChange={(e) => onChange("availability", e.target.value || null)}
          className={fieldClass}
        >
          <option value="">{t("public.market.any")}</option>
          <option value="in_stock">{t("availability.in_stock")}</option>
          <option value="on_order">{t("availability.on_order")}</option>
        </select>
      </div>

      <div>
        <label htmlFor={id("country")} className="block text-xs font-medium text-text-muted">
          {t("public.market.country")}
        </label>
        <input
          id={id("country")}
          type="text"
          maxLength={2}
          value={countryDraft}
          onChange={(e) => setCountryDraft(e.target.value)}
          onBlur={(e) => onChange("country", e.target.value.trim().toUpperCase() || null)}
          placeholder="UZ"
          className={cn(fieldClass, "num uppercase")}
        />
      </div>

      <fieldset>
        <legend className="text-xs font-medium text-text-muted">
          {t("public.market.laboratory")}
        </legend>
        {/* The checkbox is 16px and always will be — it is the ROW that has to
            be tappable, so the label carries the height and the whole strip
            toggles. */}
        <div className="mt-1 space-y-0.5">
          <label className="flex min-h-11 items-center gap-2.5 rounded-md px-2 text-sm text-text-muted transition-colors hover:bg-surface-2 lg:min-h-0 lg:px-0 lg:py-1.5">
            <input
              type="checkbox"
              checked={state.hasPassport}
              onChange={(e) => onChange("has_lab_passport", e.target.checked ? "1" : null)}
              className="h-4 w-4 shrink-0 rounded-sm border-border-strong bg-surface-inset accent-brand"
            />
            {t("public.market.hasPassport")}
          </label>
          <label className="flex min-h-11 items-center gap-2.5 rounded-md px-2 text-sm text-text-muted transition-colors hover:bg-surface-2 lg:min-h-0 lg:px-0 lg:py-1.5">
            <input
              type="checkbox"
              checked={state.labVerified}
              onChange={(e) => onChange("lab_verified", e.target.checked ? "1" : null)}
              className="h-4 w-4 shrink-0 rounded-sm border-border-strong bg-surface-inset accent-brand"
            />
            {t("public.market.labVerified")}
          </label>
        </div>
      </fieldset>
    </div>
  );
}
