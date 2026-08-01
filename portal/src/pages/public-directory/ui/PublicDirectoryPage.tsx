import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { PublicCompanyTile, usePublicDirectory } from "@/entities/public";
import { directoryBySlug, publicSiteOrigin } from "@/shared/config";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { Seo, useCanonical } from "@/shared/seo";
import { LinkButton, Skeleton } from "@/shared/ui";
import { useTierBase } from "@/shared/lib";

const PAGE_SIZE = 24;

/**
 * One page serving `/manufacturers`, `/traders`, `/logistics` and
 * `/laboratories`.
 *
 * They differ by a slug and a heading, so four page components would be four
 * places for the empty state, the pagination or the metadata to drift. The slug
 * comes from the route and is validated against `PUBLIC_DIRECTORIES`, so an
 * unknown one renders the not-found branch instead of querying the API with
 * whatever was in the URL.
 */
export function PublicDirectoryPage({ slug }: { slug: string }) {
  const base = useTierBase();
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const directory = directoryBySlug(slug);

  const origin = publicSiteOrigin();
  const { canonical, alternates } = useCanonical(
    origin,
    `/${slug}`,
    SUPPORTED_LANGS,
    i18n.language,
  );

  const q = params.get("q") ?? "";
  const country = (params.get("country") ?? "").toUpperCase();
  const offset = Math.max(0, Number(params.get("offset") ?? 0) || 0);
  const isFiltered = Boolean(q || country);

  const query = usePublicDirectory(
    directory?.slug ?? "",
    q,
    country,
    offset,
    PAGE_SIZE,
  );
  const total = query.data?.total ?? 0;

  if (!directory) {
    return (
      <div className="mx-auto max-w-[1440px] px-4 py-20 text-center lg:px-6">
        <h1 className="text-2xl font-semibold text-text">{t("public.directory.notFound")}</h1>
        <div className="mt-6">
          <LinkButton to={base || "/"} variant="outline">
            {t("public.nav.home")}
          </LinkButton>
        </div>
      </div>
    );
  }

  function setFilter(key: string, value: string | null): void {
    const next = new URLSearchParams(params);
    if (!value) next.delete(key);
    else next.set(key, value);
    next.delete("offset");
    setParams(next);
  }

  function goToOffset(nextOffset: number): void {
    const next = new URLSearchParams(params);
    if (nextOffset <= 0) next.delete("offset");
    else next.set("offset", String(nextOffset));
    setParams(next);
  }

  const heading = t(directory.labelKey);
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: t("public.nav.home"), item: `${origin}/` },
        { "@type": "ListItem", position: 2, name: heading, item: `${origin}/${directory.slug}` },
      ],
    },
    ...(query.data && query.data.items.length > 0
      ? [
          {
            "@context": "https://schema.org",
            "@type": "ItemList",
            name: heading,
            numberOfItems: total,
            itemListElement: query.data.items.map((company, index) => ({
              "@type": "ListItem",
              position: offset + index + 1,
              url: `${origin}/${directory.slug}/${company.id}`,
              name: company.short_name ?? company.legal_name ?? undefined,
            })),
          },
        ]
      : []),
  ];

  return (
    <>
      <Seo
        title={t("public.directory.metaTitle", { name: heading })}
        description={t(directory.subtitleKey)}
        canonical={canonical}
        alternates={isFiltered ? undefined : alternates}
        noindex={isFiltered}
        jsonLd={jsonLd}
      />

      <div className="mx-auto max-w-[1440px] px-4 py-10 lg:px-6">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight text-text">{heading}</h1>
          <p className="mt-1 max-w-[70ch] text-sm text-text-muted">
            {t(directory.subtitleKey)}
          </p>
        </header>

        <div className="mt-6 grid gap-3 sm:grid-cols-[minmax(0,1fr)_8rem]">
          <div>
            <label htmlFor="dir-q" className="sr-only">
              {t("public.directory.search")}
            </label>
            <input
              id="dir-q"
              type="search"
              defaultValue={q}
              onBlur={(e) => setFilter("q", e.target.value.trim() || null)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setFilter("q", (e.target as HTMLInputElement).value.trim() || null);
                }
              }}
              placeholder={t("public.directory.searchPlaceholder")}
              className="h-10 w-full rounded-md border border-border bg-surface-inset px-3 text-sm text-text placeholder:text-text-subtle focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
          </div>
          <div>
            <label htmlFor="dir-country" className="sr-only">
              {t("public.market.country")}
            </label>
            <input
              id="dir-country"
              type="text"
              maxLength={2}
              defaultValue={country}
              onBlur={(e) => setFilter("country", e.target.value.trim().toUpperCase() || null)}
              placeholder="UZ"
              className="num h-10 w-full rounded-md border border-border bg-surface-inset px-3 text-sm uppercase text-text placeholder:text-text-subtle focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
          </div>
        </div>

        <p className="mt-5 text-sm text-text-muted" aria-live="polite">
          {query.isLoading ? (
            <Skeleton className="h-5 w-40" />
          ) : (
            t("public.directory.resultCount", { count: total })
          )}
        </p>

        {query.isLoading ? (
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <Skeleton className="h-44 w-full" />
            <Skeleton className="h-44 w-full" />
            <Skeleton className="h-44 w-full" />
          </div>
        ) : query.isError ? (
          <p className="mt-4 rounded-lg border border-border bg-surface px-4 py-10 text-center text-sm text-text-muted">
            {t("errors.loadFailed")}
          </p>
        ) : query.data && query.data.items.length > 0 ? (
          <>
            <ul className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {query.data.items.map((company) => (
                <li key={company.id} className="min-w-0">
                  <PublicCompanyTile company={company} slug={directory.slug} />
                </li>
              ))}
            </ul>

            {total > PAGE_SIZE ? (
              <nav
                aria-label={t("public.market.pagination")}
                className="mt-8 flex items-center justify-between gap-4"
              >
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => goToOffset(offset - PAGE_SIZE)}
                  className="rounded-md border border-border-strong px-4 py-2 text-sm font-medium text-text transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:text-text-subtle disabled:hover:bg-transparent"
                >
                  {t("common.prev")}
                </button>
                <span className="num text-sm text-text-muted">
                  {t("public.market.pageOf", {
                    page: Math.floor(offset / PAGE_SIZE) + 1,
                    pages: Math.max(1, Math.ceil(total / PAGE_SIZE)),
                  })}
                </span>
                <button
                  type="button"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => goToOffset(offset + PAGE_SIZE)}
                  className="rounded-md border border-border-strong px-4 py-2 text-sm font-medium text-text transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:text-text-subtle disabled:hover:bg-transparent"
                >
                  {t("common.next")}
                </button>
              </nav>
            ) : null}
          </>
        ) : (
          <div className="mt-4 rounded-lg border border-border bg-surface px-4 py-12 text-center">
            <p className="text-sm text-text-muted">{t("public.directory.empty")}</p>
            {isFiltered ? (
              <Link
                to={`${base}/${directory.slug}`}
                className="mt-3 inline-block text-sm text-brand hover:underline"
              >
                {t("public.market.reset")}
              </Link>
            ) : null}
          </div>
        )}
      </div>
    </>
  );
}
