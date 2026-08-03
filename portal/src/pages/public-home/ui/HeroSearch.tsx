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
        className="rounded-lg border border-border/60 bg-bg/40 p-1.5 shadow-hero-lift backdrop-blur-sm transition-shadow focus-within:border-brand-line focus-within:shadow-glow sm:p-2.5"
      >
        {/*
          One row at every width — the mockup's shape, and the only one that
          reads as a search BAR on a phone.

          Two earlier passes got this wrong in the same way, by giving the
          submit a line of its own: first as a full-width green bar under the
          field, then as a ~60% one sharing a wrapped row with the scope. Both
          made the bright `--hero-field` plate 128px tall with a 212px green
          button sitting in it, which is not a search control — it is a form
          card, and it competed with the hero's actual CTA 60px below it.

          What the phone row carries is therefore the irreducible pair, a field
          and a way to submit it: the scope select is desktop-only (see below),
          and the submit drops its label to the square glyph the space allows —
          44px, still the brightest thing in the assembly, just no longer the
          biggest. Between them the query field keeps ~284px of a 332px row.
        */}
        <div className="flex min-w-0 flex-nowrap items-center rounded-md bg-hero-field p-1">
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
              className="h-11 w-full rounded-sm bg-transparent px-3 text-[15px] text-hero-field-fg placeholder:text-hero-field-fg/55 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand sm:h-[3.25rem] sm:px-4"
            />
          </div>

          {/*
            Desktop only. On a phone the scope cost ~100px of a ~262–332px row
            — a third of the bar — to set a value that is already right: the
            default is `products`, which is what a storefront search means, and
            the two other scopes have a more direct route on that screen than a
            dropdown inside a search field. The six directory cards sit one
            swipe below the hero and go straight to companies, logistics and
            labs.

            It stays mounted, just not rendered, so `scope` keeps its
            `products` default and `onSubmit` lands on `/market?q=` without a
            phone-specific branch.

            The divider is a hairline in the field's own ink so the controls
            read as one pill split into parts, rather than separate chips.
            `/10`, not `/12`: bare opacity modifiers come from `theme.opacity`
            and step by 5, and an off-step one compiles to nothing without
            complaining.
          */}
          <div className="relative hidden shrink-0 items-center border-s border-hero-field-fg/10 sm:flex">
            <label htmlFor="hero-search-scope" className="sr-only">
              {t("public.home.searchScope")}
            </label>
            <select
              id="hero-search-scope"
              value={scope}
              onChange={(e) => setScope(e.target.value as (typeof SEARCH_SCOPES)[number])}
              className="h-[3.25rem] appearance-none rounded-sm bg-transparent pe-8 ps-4 text-sm font-medium text-hero-field-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
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

          {/* The label is `hidden`, which takes it out of the accessibility
              tree as well as the layout — hence the explicit `aria-label`, so
              the glyph-only phone button still announces itself. */}
          <button
            type="submit"
            aria-label={t("public.home.searchAction")}
            className="ms-1 inline-flex h-11 w-11 shrink-0 items-center justify-center gap-2 rounded-sm bg-brand text-[15px] font-semibold text-brand-fg transition-all hover:brightness-110 hover:shadow-glow active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-hero-field sm:ms-0 sm:h-[3.25rem] sm:w-auto sm:px-8"
          >
            <Search size={18} strokeWidth={2.25} aria-hidden />
            <span className="hidden sm:inline">{t("public.home.searchAction")}</span>
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
      {/*
        The row is masked at its trailing edge rather than cut by the viewport.
        Scrolled content that simply stops at x=390 reads as a rendering fault
        — «PVC» sliced down the middle — where a fade reads as "there is more
        this way". The mask only exists while the row can actually scroll, i.e.
        below `xl`, where the shell widens enough to hold all nine links.
      */}
      <div className="mt-3.5 [--fade:theme(spacing.6)] [mask-image:linear-gradient(to_right,#000_calc(100%-var(--fade)),transparent)] xl:[mask-image:none]">
        <div className="flex items-center gap-2 overflow-x-auto px-1 pb-1 pe-6 [scrollbar-width:none] xl:pe-1 [&::-webkit-scrollbar]:hidden">
          <span className="shrink-0 text-[11px] text-text-muted sm:text-xs">
            {t("public.home.popular")}
          </span>
          {POPULAR.map((term) => (
            <Link
              key={term.q}
              to={`/market?q=${encodeURIComponent(term.q)}`}
              /* `h-10`, not `py-1`: these measured 27px tall, and they are the
                 hero's only one-tap route into the catalog. Height only —
                 `px-3` is load-bearing at `xl`, where the eight queries plus
                 «Все запросы» measure ~790px inside an 800px shell. Widening
                 the padding by 4px a side pushed the row to 822 and clipped the
                 last link off the end. */
              className="num inline-flex h-10 shrink-0 items-center rounded-full border border-border bg-surface/80 px-3 text-[11px] font-medium text-text transition-colors hover:border-brand-line hover:bg-brand-soft hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg sm:text-xs"
            >
              {term.labelKey ? t(term.labelKey) : term.q}
            </Link>
          ))}
          <Link
            to="/market"
            className="ms-1 inline-flex h-9 shrink-0 items-center gap-1 pe-1 text-[11px] font-medium text-brand underline underline-offset-2 sm:text-xs"
          >
            {t("public.home.allQueries")}
            <span aria-hidden>→</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
