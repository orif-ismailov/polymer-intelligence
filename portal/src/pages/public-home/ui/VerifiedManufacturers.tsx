import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { usePublicDirectory, type PublicCompanyCard } from "@/entities/public";
import { countryFlag, countryName } from "@/shared/lib";
import { RegistryIcon, Skeleton } from "@/shared/ui";

function ManufacturerTile({ company }: { company: PublicCompanyCard }) {
  const { t, i18n } = useTranslation();
  const name = company.short_name ?? company.legal_name ?? t("public.company.untitled");
  const flag = countryFlag(company.jurisdiction);

  return (
    <Link
      to={`/manufacturers/${company.id}`}
      /* Fixed 136px on the phone rail, auto in the desktop grid. */
      className="group flex w-[8.5rem] shrink-0 snap-start flex-col rounded-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand md:w-auto md:min-w-0 md:shrink"
    >
      <span className="flex h-[4.5rem] w-full items-center justify-center overflow-hidden rounded-md bg-[color-mix(in_srgb,var(--text)_96%,transparent)] px-2">
        {company.logo_url ? (
          <img
            src={company.logo_url}
            alt=""
            loading="lazy"
            className="max-h-12 max-w-full object-contain"
          />
        ) : (
          <span className="text-bg">
            <RegistryIcon size={24} />
          </span>
        )}
      </span>

      {/*
        Two lines' worth of height whether the name needs them or not. Company
        names run one line («Chirchiq Cable») or two («Andijan Polymer Pipe»),
        and letting the box be content-height pushed everything under it up by
        a line on the short ones — so across a row the flags, the offer counts
        and the ruled «Производитель» footers all landed at different heights.
        Reserving the taller case is what makes the row read as a row; it is
        the same 2.375rem at every width, so the desktop grid squares up too.
      */}
      <span className="mt-2.5 line-clamp-2 min-h-[2.375rem] text-[13px] font-semibold leading-[1.15] text-text group-hover:text-brand">
        {name}
      </span>
      <span className="mt-1.5 flex min-w-0 items-center gap-1.5 text-[11px] text-text-muted">
        {flag ? (
          <span aria-hidden className="text-[12px] leading-none">
            {flag}
          </span>
        ) : null}
        <span className="truncate">{countryName(company.jurisdiction, i18n.language)}</span>
      </span>
      {/*
        The mockup shows a ★ rating here. Nothing in the platform produces one —
        there is no rating column and no deal-feedback surface — so the slot
        carries a real figure instead of an invented number.
      */}
      <span className="num mt-1.5 text-[11px] text-text-subtle">
        {t("public.home.manufacturerOffers", { count: company.offer_count })}
      </span>
      <span className="mt-2.5 border-t border-border pt-2 text-[10px] text-text-subtle">
        {t("public.role.manufacturer")}
      </span>
    </Link>
  );
}

/**
 * Verified-manufacturer tiles under recommended products (marketplace.jpeg §4),
 * the second panel of the middle column.
 *
 * A six-up grid, not a horizontal scroller: the mockup fits all six across the
 * column, and the scroller this replaces clipped the last tile off the right
 * edge at every desktop width.
 */
/*
 * Snap rail on a phone, six-up grid from `md`.
 *
 * Three across at 390 gave each tile 105px, which is narrower than most of
 * these names and forced the two-line wrap that made the rows ragged; two
 * across would have run the block to three rows. Swiping one row of six is
 * both shorter and the idiom a phone user already has for "a shelf of
 * brands". `-mx-3.5 px-3.5` lets the scroll area reach the card's edges while
 * the first tile still starts on the card's padding, so a mid-scroll tile
 * bleeds off the edge instead of stopping short of it.
 */
const railClass =
  "-mx-3.5 mt-3.5 flex snap-x snap-mandatory gap-3 overflow-x-auto px-3.5 pb-1 " +
  "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden " +
  "md:mx-0 md:grid md:grid-cols-6 md:gap-3.5 md:overflow-visible md:px-0 md:pb-0";

export function VerifiedManufacturers() {
  const { t } = useTranslation();
  const directory = usePublicDirectory("manufacturers", "", "", 0, 6);

  return (
    <section
      aria-labelledby="verified-manufacturers"
      className="rounded-md border border-border bg-surface p-3.5"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 id="verified-manufacturers" className="text-[15px] font-semibold text-text">
          {t("public.home.verifiedManufacturers")}
        </h3>
        <Link
          to="/manufacturers"
          className="shrink-0 text-[12px] font-medium text-brand hover:underline"
        >
          {t("public.home.seeAllPeople")}
          <span aria-hidden> →</span>
        </Link>
      </div>

      {directory.isLoading ? (
        <div className={railClass}>
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-40 w-[8.5rem] shrink-0 md:w-full" />
          ))}
        </div>
      ) : directory.data && directory.data.items.length > 0 ? (
        <div className={railClass}>
          {directory.data.items.map((company) => (
            <ManufacturerTile key={company.id} company={company} />
          ))}
        </div>
      ) : (
        <p className="mt-3.5 rounded-md border border-border bg-surface-inset px-4 py-8 text-center text-sm text-text-muted">
          {t("public.directory.empty")}
        </p>
      )}
    </section>
  );
}
