import { type ReactNode } from "react";

import {
  BarChart3,
  ChevronRight,
  Factory,
  FlaskConical,
  Handshake,
  Newspaper,
  Truck,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { usePublicStats } from "@/entities/public";
import { PUBLIC_DIRECTORIES } from "@/shared/config";
import { Skeleton } from "@/shared/ui";

const DIRECTORY_ICONS: Record<string, ReactNode> = {
  manufacturers: <Factory size={32} strokeWidth={1.5} aria-hidden />,
  traders: <Handshake size={32} strokeWidth={1.5} aria-hidden />,
  logistics: <Truck size={32} strokeWidth={1.5} aria-hidden />,
  laboratories: <FlaskConical size={32} strokeWidth={1.5} aria-hidden />,
};

const DIRECTORY_BODY_KEYS: Record<string, string> = {
  manufacturers: "public.home.directoryCard.manufacturersBody",
  traders: "public.home.directoryCard.tradersBody",
  logistics: "public.home.directoryCard.logisticsBody",
  laboratories: "public.home.directoryCard.laboratoriesBody",
};

/**
 * Six equal entry cards under the hero (marketplace.jpeg §3): 224x115 on the
 * 1440 layout, 10px apart — a 30px brand glyph in a left column, title and a
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
      icon: <BarChart3 size={32} strokeWidth={1.5} aria-hidden />,
      title: t("public.nav.prices"),
      body: t("public.home.directoryCard.pricesBody"),
      meta: t("public.home.directoryCard.daily"),
    },
    {
      key: "news",
      to: "/news",
      icon: <Newspaper size={32} strokeWidth={1.5} aria-hidden />,
      title: t("public.nav.news"),
      body: t("public.home.directoryCard.newsBody"),
      meta: t("public.home.directoryCard.daily"),
    },
  ];

  const cardClass =
    "group flex min-h-[7.1875rem] flex-col justify-between rounded-md border border-border bg-surface p-4 transition-colors hover:border-brand-line hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg";

  return (
    <section
      aria-labelledby="directories-heading"
      className="mx-auto max-w-[1440px] px-4 pt-6 lg:px-6 lg:pt-8"
    >
      <h2 id="directories-heading" className="sr-only">
        {t("public.home.directoriesHeading")}
      </h2>
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {PUBLIC_DIRECTORIES.map((dir) => {
          const count = stats.data?.directory_counts?.[dir.role] ?? 0;
          const bodyKey = DIRECTORY_BODY_KEYS[dir.slug];
          return (
            <Link key={dir.slug} to={`/${dir.slug}`} className={cardClass}>
              <div className="flex items-start gap-3.5">
                <span className="shrink-0 text-brand">
                  {DIRECTORY_ICONS[dir.slug]}
                </span>
                <div className="min-w-0">
                  <h3 className="text-[15px] font-semibold leading-snug text-text">
                    {t(dir.labelKey)}
                  </h3>
                  <p className="mt-1.5 line-clamp-2 text-[11px] leading-[1.45] text-text-muted">
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
            <div className="flex items-start gap-3.5">
              <span className="shrink-0 text-brand">{item.icon}</span>
              <div className="min-w-0">
                <h3 className="text-[15px] font-semibold leading-snug text-text">{item.title}</h3>
                <p className="mt-1.5 line-clamp-2 text-[11px] leading-[1.45] text-text-muted">
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
