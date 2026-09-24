import type { ReactNode } from "react";

import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import {
  TechnologistTile,
  useTechFacets,
  useTechnologists,
  type TechnologistFilters,
} from "@/entities/technologist";
import { publicSiteOrigin } from "@/shared/config";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { useSyncedDraft } from "@/shared/lib";
import { Seo, useCanonical } from "@/shared/seo";
import {
  FactoryIcon,
  IconTile,
  LinkButton,
  PageHeader,
  PageShell,
  Pagination,
  Select,
  Skeleton,
  UsersIcon,
} from "@/shared/ui";

export const TECHNOLOGISTS_PAGE_SIZE = 24;

/**
 * `/technologists` — both sides of the expert marketplace on one page.
 *
 * The two CTAs are the brief's «I NEED A TECHNOLOGIST» / «I AM A TECHNOLOGIST»:
 * IMEX is the meeting place, not the employer, so the page speaks to the
 * factory and to the expert with equal weight. Below them, the catalog —
 * server-rendered and filterable through the URL, like the company directories.
 */
export function TechnologistsPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const origin = publicSiteOrigin();
  const { canonical, alternates } = useCanonical(
    origin,
    "/technologists",
    SUPPORTED_LANGS,
    i18n.language,
  );

  const filters: TechnologistFilters = {
    process: params.get("process") ?? "",
    material: params.get("material") ?? "",
    language: params.get("language") ?? "",
    country: (params.get("country") ?? "").toUpperCase(),
    q: params.get("q") ?? "",
  };
  const offset = Math.max(0, Number(params.get("offset") ?? 0) || 0);
  const isFiltered = Object.values(filters).some(Boolean);
  const [qDraft, setQDraft] = useSyncedDraft(filters.q ?? "");

  const facets = useTechFacets();
  const query = useTechnologists(filters, offset, TECHNOLOGISTS_PAGE_SIZE);
  const total = query.data?.total ?? 0;

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

  const any = { value: "", label: t("technologists.filters.any") };
  const heading = t("technologists.title");

  return (
    <>
      <Seo
        title={t("technologists.metaTitle")}
        description={t("technologists.subtitle")}
        canonical={canonical}
        alternates={isFiltered ? undefined : alternates}
        noindex={isFiltered}
      />

      <PageShell width="storefront">
        <PageHeader title={heading} subtitle={t("technologists.subtitle")} />

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <SideCard
            icon={<FactoryIcon size={22} />}
            title={t("technologists.needTitle")}
            body={t("technologists.needBody")}
            cta={t("technologists.needCta")}
            to="/cabinet/tech-requests/new"
            testId="tech-cta-need"
          />
          <SideCard
            icon={<UsersIcon size={22} />}
            title={t("technologists.amTitle")}
            body={t("technologists.amBody")}
            cta={t("technologists.amCta")}
            to="/cabinet/register?as=technologist"
            variant="outline"
            testId="tech-cta-am"
          />
        </div>

        <h2 className="mt-10 text-lg font-semibold text-text">{t("technologists.catalogTitle")}</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.5fr)_repeat(3,minmax(0,1fr))_6rem]">
          <div>
            <label htmlFor="tech-q" className="sr-only">
              {t("technologists.filters.search")}
            </label>
            <input
              id="tech-q"
              type="search"
              value={qDraft}
              onChange={(e) => setQDraft(e.target.value)}
              onBlur={(e) => setFilter("q", e.target.value.trim() || null)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setFilter("q", (e.target as HTMLInputElement).value.trim() || null);
                }
              }}
              placeholder={t("technologists.filters.searchPlaceholder")}
              className="h-10 w-full rounded-md border border-border bg-surface-inset px-3 text-sm text-text placeholder:text-text-subtle focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
          </div>
          <Select
            aria-label={t("technologists.filters.process")}
            value={filters.process}
            onChange={(e) => setFilter("process", e.target.value || null)}
            options={[
              { ...any, label: t("technologists.filters.anyProcess") },
              ...(facets.data?.processes ?? []).map((p) => ({
                value: p,
                label: t(`technologists.process.${p}`),
              })),
            ]}
          />
          <Select
            aria-label={t("technologists.filters.material")}
            value={filters.material}
            onChange={(e) => setFilter("material", e.target.value || null)}
            options={[
              { ...any, label: t("technologists.filters.anyMaterial") },
              ...(facets.data?.materials ?? []).map((m) => ({ value: m, label: m })),
            ]}
          />
          <Select
            aria-label={t("technologists.filters.language")}
            value={filters.language}
            onChange={(e) => setFilter("language", e.target.value || null)}
            options={[
              { ...any, label: t("technologists.filters.anyLanguage") },
              ...(facets.data?.languages ?? []).map((l) => ({
                value: l,
                label: t(`technologists.language.${l}`),
              })),
            ]}
          />
          <div>
            <label htmlFor="tech-country" className="sr-only">
              {t("public.market.country")}
            </label>
            <input
              id="tech-country"
              type="text"
              maxLength={2}
              defaultValue={filters.country}
              key={filters.country}
              onBlur={(e) => setFilter("country", e.target.value.trim().toUpperCase() || null)}
              placeholder="UZ"
              className="num h-10 w-full rounded-md border border-border bg-surface-inset px-3 text-sm uppercase text-text placeholder:text-text-subtle focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
          </div>
        </div>

        <div className="mt-5 text-sm text-text-muted" aria-live="polite">
          {query.isLoading ? (
            <Skeleton className="h-5 w-40" />
          ) : (
            t("technologists.resultCount", { count: total })
          )}
        </div>

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
              {query.data.items.map((card) => (
                <li key={card.id} className="min-w-0">
                  <TechnologistTile card={card} />
                </li>
              ))}
            </ul>
            <Pagination
              offset={offset}
              total={total}
              pageSize={TECHNOLOGISTS_PAGE_SIZE}
              onChange={goToOffset}
              label={t("public.market.pagination")}
              prevLabel={t("common.prev")}
              nextLabel={t("common.next")}
              pageOfLabel={(page, pages) => t("public.market.pageOf", { page, pages })}
            />
          </>
        ) : (
          <div className="mt-4 rounded-lg border border-border bg-surface px-4 py-12 text-center">
            <p className="text-sm text-text-muted">{t("technologists.empty")}</p>
            {isFiltered ? (
              <Link to="/technologists" className="mt-3 inline-block text-sm text-brand hover:underline">
                {t("public.market.reset")}
              </Link>
            ) : null}
          </div>
        )}
      </PageShell>
    </>
  );
}

function SideCard({
  icon,
  title,
  body,
  cta,
  to,
  variant = "primary",
  testId,
}: {
  icon: ReactNode;
  title: string;
  body: string;
  cta: string;
  to: string;
  variant?: "primary" | "outline";
  testId: string;
}) {
  return (
    <section className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5">
      <div className="flex items-start gap-3">
        <IconTile tone="brand">{icon}</IconTile>
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-text">{title}</h2>
          <p className="mt-1 text-sm text-text-muted">{body}</p>
        </div>
      </div>
      <LinkButton to={to} variant={variant} className="mt-auto self-start" data-testid={testId}>
        {cta}
      </LinkButton>
    </section>
  );
}
