import { useState, type FormEvent } from "react";

import { ChevronDown, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

/**
 * The storefront's primary conversion control.
 *
 * Shape is the mockup's (`docs/new-design/marketplace.jpeg` §2): ONE bright pill
 * carrying the input, the scope select and the brand CTA — the button is a child
 * of the pill, not a sibling beside it. Two things changed when the hero went
 * full-bleed:
 *
 * - **It is left-aligned in the copy column** instead of centred across a card.
 *   At 1440 the mockup's shell spanned 256→1183 because the hero was 431px tall
 *   and the search was the only thing that could fill its foot; with a real copy
 *   column the search belongs to the headline it answers.
 * - **The fill is a token.** It used to be `color-mix(--text 97%)`, i.e. "the
 *   inverse of the body colour", which is white only while the theme is dark —
 *   on the light page it rendered as a black bar. `--hero-field` states the
 *   intent instead: this control is the brightest plane in the hero, in both
 *   themes.
 */

const POPULAR: ReadonlyArray<{ q: string; labelKey?: string }> = [
  { q: "HDPE" },
  { q: "PP" },
  { q: "LLDPE" },
  { q: "PVC" },
  { q: "PET" },
  { q: "PS" },
  { q: "Каучук", labelKey: "public.home.popularTag.rubber" },
  { q: "Растворители", labelKey: "public.home.popularTag.solvents" },
];

const SEARCH_SCOPES = ["products", "companies", "services"] as const;

export function HeroSearch() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [scope, setScope] = useState<(typeof SEARCH_SCOPES)[number]>("products");

  function onSubmit(e: FormEvent): void {
    e.preventDefault();
    const term = q.trim();
    if (scope === "companies") {
      void navigate(term ? `/manufacturers?q=${encodeURIComponent(term)}` : "/manufacturers");
      return;
    }
    if (scope === "services") {
      void navigate(term ? `/logistics?q=${encodeURIComponent(term)}` : "/logistics");
      return;
    }
    void navigate(term ? `/market?q=${encodeURIComponent(term)}` : "/market");
  }

  return (
    /*
     * Wider at `xl` than the pill strictly needs: the eight popular queries plus
     * «Все запросы» measure ~790px, so at 44rem the last link wrapped onto a
     * second line of its own. The row below the field sets this width, not the
     * field.
     */
    <div className="w-full max-w-[44rem] xl:max-w-[50rem]">
      <form
        onSubmit={onSubmit}
        /*
         * The shell is a soft halo around the pill rather than a second border:
         * on a photo, a hairline reads as a cut-out, a blurred pad reads as a
         * control resting on the image. The ring lifts on focus-within so the
         * whole assembly answers the keyboard, not just the field inside it.
         */
        className="rounded-lg border border-border/60 bg-bg/40 p-2 shadow-hero-lift backdrop-blur-sm transition-shadow focus-within:border-brand-line focus-within:shadow-glow sm:p-2.5"
      >
        <div className="flex min-w-0 flex-col gap-1.5 rounded-md bg-hero-field p-1 sm:flex-row sm:items-center sm:gap-0">
          {/*
            Query and scope travel together at every width. Stacking all THREE
            controls on a phone gave the scope select a full-width row of its
            own, which read as a second field and cost ~52px in a band that was
            already over a screen tall. They are one question — "find X, in Y".
          */}
          <div className="flex min-w-0 flex-1 items-center">
            <div className="relative min-w-0 flex-1">
              <label htmlFor="hero-search" className="sr-only">
                {t("public.home.searchLabel")}
              </label>
              <input
                id="hero-search"
                type="search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t("public.home.searchPlaceholder")}
                className="h-12 w-full rounded-sm bg-transparent px-4 text-[15px] text-hero-field-fg placeholder:text-hero-field-fg/55 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand sm:h-[3.25rem]"
              />
            </div>

            {/* Hairline in the field's own ink so the controls read as one pill
                split into parts, rather than separate chips. `/10`, not `/12`:
                bare opacity modifiers come from `theme.opacity` and step by 5,
                and an off-step one compiles to nothing without complaining. */}
            <div className="relative flex shrink-0 items-center border-s border-hero-field-fg/10">
              <label htmlFor="hero-search-scope" className="sr-only">
                {t("public.home.searchScope")}
              </label>
              <select
                id="hero-search-scope"
                value={scope}
                onChange={(e) => setScope(e.target.value as (typeof SEARCH_SCOPES)[number])}
                className="h-12 appearance-none rounded-sm bg-transparent pe-8 ps-3 text-sm font-medium text-hero-field-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand sm:ps-4 sm:h-[3.25rem]"
              >
                {SEARCH_SCOPES.map((key) => (
                  <option key={key} value={key} className="bg-surface text-text">
                    {t(`public.home.scope.${key}`)}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={16}
                strokeWidth={1.75}
                aria-hidden
                className="pointer-events-none absolute end-3 text-hero-field-fg"
              />
            </div>
          </div>

          <button
            type="submit"
            className="inline-flex h-12 shrink-0 items-center justify-center gap-2 rounded-sm bg-brand px-8 text-[15px] font-semibold text-brand-fg transition-all hover:brightness-110 hover:shadow-glow active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-hero-field sm:h-[3.25rem]"
          >
            <Search size={17} strokeWidth={2.25} aria-hidden />
            {t("public.home.searchAction")}
          </button>
        </div>
      </form>

      {/*
        Always one row, scrolling when it does not fit — never wrapping. Eight
        chips wrapped into three rows below the search turned the hero's most
        scannable element into its noisiest, and wrapping at exactly one width
        instead (which is what a `sm:flex-wrap` gave) just moved the mess: at
        834 it orphaned «Все запросы» onto a line of its own. At `xl` the row
        fits inside the widened shell, so the scroll never engages there and
        this is a single behaviour rather than a breakpoint story.
      */}
      <div className="mt-4 flex items-center gap-2 overflow-x-auto px-1 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <span className="shrink-0 text-[11px] text-text-muted sm:text-xs">
          {t("public.home.popular")}
        </span>
        {POPULAR.map((term) => (
          <Link
            key={term.q}
            to={`/market?q=${encodeURIComponent(term.q)}`}
            className="num shrink-0 rounded-full border border-border bg-surface/80 px-3 py-1 text-[11px] font-medium text-text transition-colors hover:border-brand-line hover:bg-brand-soft hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg sm:text-xs"
          >
            {term.labelKey ? t(term.labelKey) : term.q}
          </Link>
        ))}
        <Link
          to="/market"
          className="ms-1 inline-flex shrink-0 items-center gap-1 pe-1 text-[11px] font-medium text-brand underline underline-offset-2 sm:text-xs"
        >
          {t("public.home.allQueries")}
          <span aria-hidden>→</span>
        </Link>
      </div>
    </div>
  );
}
