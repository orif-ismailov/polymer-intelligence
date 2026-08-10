import { type ReactNode } from "react";

import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { usePublicStats } from "@/entities/public";
import { PUBLIC_DIRECTORIES } from "@/shared/config";
import { Skeleton } from "@/shared/ui";

/**
 * The commissioned icon set replacing the lucide glyphs this row used to draw:
 * detailed green renders on a transparent PNG, one per card. `alt=""` because
 * each glyph is decorative beside a real `<h3>` that already names the card.
 *
 * The `<span>` reserves the SAME square footprint the lucide glyphs held
 * (`size-6 sm:size-8`) — that box is load-bearing: it's what a browser window
 * right at 1280px (the `xl` breakpoint's own floor, before the row's
 * `max-w-[1440px]` container catches up and widens every cell) has room for
 * without truncating «Цены и аналитика». A wider reserved box measured worse
 * at that width, not better — the previous, bigger render already had zero
 * margin there before it grew any further.
 *
 * The `<img>` paints past that box on purpose: `absolute` takes it out of
 * flow, so scaling it up costs the text column nothing — it bleeds into the
 * row's own gap and the card's padding, both otherwise empty, rather than
 * eating the width `truncate` on the heading is depending on.
 */
function cardIcon(file: string): ReactNode {
  return (
    <span className="relative block size-6 shrink-0 sm:size-8">
      <img
        src={`/${file}`}
        alt=""
        aria-hidden
        className="absolute -inset-2 h-auto w-auto object-contain sm:-inset-3"
      />
    </span>
  );
}

const DIRECTORY_ICONS: Record<string, ReactNode> = {
  manufacturers: cardIcon("factory_no_bg.png"),
  traders: cardIcon("handshake_no_bg.png"),
  logistics: cardIcon("truck_logistics_no_bg.png"),
  laboratories: cardIcon("lab_flask_no_bg.png"),
};

const DIRECTORY_BODY_KEYS: Record<string, string> = {
  manufacturers: "public.home.directoryCard.manufacturersBody",
  traders: "public.home.directoryCard.tradersBody",
  logistics: "public.home.directoryCard.logisticsBody",
  laboratories: "public.home.directoryCard.laboratoriesBody",
};

/**
 * Six equal entry cards under the hero (marketplace.jpeg §3): 224x115 on the
 * 1440 layout, 10px apart — a glyph in a left column, title and a
 * two-line body beside it, count/meta + chevron on the baseline. No hairline of
 * its own above the row: the hero section closes with one, and a second rule
 * 24px below it would read as a gap rather than a join. (That rule used to
 * belong to the hero's metrics rail, which has since moved into `ProofBand`;
 * the hero carries it directly now, so nothing changes on this side.)
 */
export function DirectoryStrip() {
  const { t } = useTranslation();
  const stats = usePublicStats();

  const extras = [
    {
      key: "prices",
      to: "/prices",
      icon: cardIcon("growth_chart_no_bg.png"),
      title: t("public.nav.prices"),
      body: t("public.home.directoryCard.pricesBody"),
      meta: t("public.home.directoryCard.daily"),
    },
    {
      key: "news",
      to: "/news",
      icon: cardIcon("news_megaphone_no_bg.png"),
      title: t("public.nav.news"),
      body: t("public.home.directoryCard.newsBody"),
      meta: t("public.home.directoryCard.daily"),
    },
  ];

  /*
   * Two-up on a phone, and the 115px floor lifts with it.
   *
   * Six of these stacked full-width measured 764px — nine tenths of a screen
   * spent on six near-identical rows, each one a 32px glyph and two short lines
   * of text held apart by `min-h` from a count sitting alone on the baseline.
   * The floor exists to keep the mockup's 224x115 cell square-ish at 1440,
   * where six sit in a row; at 390 it only manufactured dead space.
   *
   * Paired at 174px each they read as a set of entry points rather than a list
   * to get past, and the block comes in around 440px.
   */
  const cardClass =
    "group flex flex-col justify-between rounded-md border border-border bg-surface p-3.5 transition-colors hover:border-brand-line hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg sm:min-h-[7.1875rem] sm:p-4";

  /*
   * The glyph leads the card on a phone instead of flanking the copy: a 32px
   * icon plus its gutter takes 46 of the 150px of usable width, which left the
   * two-line body clamping mid-word. Above the title it costs one 24px line and
   * gives the copy the whole column. The RESERVED box lives on `cardIcon()`'s
   * own `<span>` (`size-6 sm:size-8`), so every glyph shares the same layout
   * footprint regardless of its own artwork's aspect ratio — what actually
   * paints can be bigger (see that function), but this row never finds out.
   */
  const headClass = "flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-3.5";

  return (
    <section
      aria-labelledby="directories-heading"
      className="mx-auto max-w-[1440px] px-4 pt-6 lg:px-6 lg:pt-8"
    >
      <h2 id="directories-heading" className="sr-only">
        {t("public.home.directoriesHeading")}
      </h2>
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-3 xl:grid-cols-6">
        {PUBLIC_DIRECTORIES.map((dir) => {
          const count = stats.data?.directory_counts?.[dir.role] ?? 0;
          const bodyKey = DIRECTORY_BODY_KEYS[dir.slug];
          return (
            <Link key={dir.slug} to={`/${dir.slug}`} className={cardClass}>
              <div className={headClass}>
                {DIRECTORY_ICONS[dir.slug]}
                <div className="min-w-0">
                  <h3 className="truncate text-[13px] font-semibold leading-snug text-text sm:text-[15px]">
                    {t(dir.labelKey)}
                  </h3>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-[1.45] text-text-muted sm:mt-1.5">
                    {bodyKey ? t(bodyKey) : t(dir.subtitleKey)}
                  </p>
                </div>
              </div>
              <div className="mt-3 flex items-end justify-between gap-2">
                <p className="num text-[11px] text-text-muted">
                  {stats.isLoading ? (
                    <Skeleton className="h-3.5 w-20" />
                  ) : (
                    t("public.home.companyCount", { count })
                  )}
                </p>
                <ChevronRight
                  size={16}
                  strokeWidth={1.75}
                  aria-hidden
                  className="text-text-subtle transition-colors group-hover:text-brand"
                />
              </div>
            </Link>
          );
        })}

        {extras.map((item) => (
          <Link key={item.key} to={item.to} className={cardClass}>
            <div className={headClass}>
              {item.icon}
              <div className="min-w-0">
                <h3 className="truncate text-[13px] font-semibold leading-snug text-text sm:text-[15px]">
                  {item.title}
                </h3>
                <p className="mt-1 line-clamp-2 text-[11px] leading-[1.45] text-text-muted sm:mt-1.5">
                  {item.body}
                </p>
              </div>
            </div>
            <div className="mt-3 flex items-end justify-between gap-2">
              <p className="text-[11px] text-text-muted">{item.meta}</p>
              <ChevronRight
                size={16}
                strokeWidth={1.75}
                aria-hidden
                className="text-text-subtle transition-colors group-hover:text-brand"
              />
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
