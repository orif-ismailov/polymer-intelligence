import { type CSSProperties } from "react";

import { useTranslation } from "react-i18next";

import { usePublicStats } from "@/entities/public";
import { cn, useCountUp } from "@/shared/lib";
import { Skeleton } from "@/shared/ui";

interface FigureSpec {
  key: string;
  value: number | undefined;
  suffix: string;
  label: string;
  /** Measured by the platform, as opposed to a claim we make about it. */
  live: boolean;
  decimals?: number;
  /**
   * Floor below which a live figure is not worth stating. Only meaningful for
   * live rows — a claim has no data to be embarrassed by.
   */
  floor?: number;
}

/**
 * Column counts as whole literal strings. Tailwind's scanner reads source text,
 * not runtime values, so `xl:grid-cols-${n}` would compile to nothing — the same
 * silent class that `docs/design-system.md` P3.1 warns about, just arrived at by
 * string interpolation instead of by a missing token.
 */
const COLUMNS: Record<number, string> = {
  3: "grid-cols-1 sm:grid-cols-3",
  4: "grid-cols-2 sm:grid-cols-2 xl:grid-cols-4",
  5: "grid-cols-2 sm:grid-cols-3 xl:grid-cols-5",
  6: "grid-cols-2 sm:grid-cols-3 xl:grid-cols-6",
};

interface FigureProps {
  spec: FigureSpec;
  loading: boolean;
  revealed: boolean;
  liveLabel: string;
  delayMs: number;
}

/**
 * A single figure. Its own component because `useCountUp` is a hook and the
 * figures are a `.map()` — calling it in the loop body would break the rules of
 * hooks the moment the row count changes, which is exactly what the floor below
 * makes it do.
 */
function Figure({ spec, loading, revealed, liveLabel, delayMs }: FigureProps) {
  const { i18n } = useTranslation();
  const target = spec.value ?? 0;
  const shown = useCountUp(target, { enabled: revealed, decimals: spec.decimals ?? 0 });

  return (
    <div
      data-reveal
      style={{ "--reveal-delay": `${delayMs}ms` } as CSSProperties}
      className="flex flex-col border-s border-t border-border bg-surface px-4 py-6 text-center sm:px-5 sm:py-7"
    >
      {/* Flex `order` puts the figure above its label while the markup keeps the
          <dt>-before-<dd> sequence a <dl> requires — same arrangement the hero
          rail used. */}
      <dt className="order-2 mt-2 flex items-center justify-center gap-1.5 text-xs leading-snug text-text-muted">
        {/*
          Marks the three figures the API actually measures, so the band is
          honest about which numbers are counted and which are claimed — the
          distinction the old component kept in a `live` flag that never reached
          the screen.
        */}
        {spec.live ? (
          <>
            <span
              aria-hidden
              className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand motion-safe:animate-pulse"
            />
            <span className="sr-only">{liveLabel}</span>
          </>
        ) : null}
        {spec.label}
      </dt>
      <dd className="num order-1 text-[1.75rem] font-semibold leading-none tracking-tight text-text sm:text-[2.125rem] xl:text-[2.375rem]">
        {loading ? (
          <Skeleton className="mx-auto h-9 w-24" />
        ) : (
          <>
            {shown.toLocaleString(i18n.language, {
              maximumFractionDigits: spec.decimals ?? 0,
              minimumFractionDigits: spec.decimals ?? 0,
            })}
            {/*
              The accent punctuates the figure instead of flooding it. Six neon
              numbers would break the palette's "one bright accent per view";
              six near-white numbers with a green tick after each one keep the
              scale and stay legible.
            */}
            <span className="text-brand">{spec.suffix}</span>
          </>
        )}
      </dd>
    </div>
  );
}

/**
 * «Платформа в цифрах» — the band's proof block.
 *
 * Two things changed from the bar this replaces. The heading is no longer
 * `sr-only`, so the section actually says what the numbers are; and a live
 * figure under its floor is dropped rather than published. `country_count` sits
 * at 1 today, and "1+ Стран" directly under a «Международная платформа» card
 * argues against the band it belongs to. The row reflows and self-heals as the
 * data grows — no hardcoding, no number we do not have.
 */
export function PlatformFigures({ revealed }: { revealed: boolean }) {
  const { t } = useTranslation();
  const stats = usePublicStats();

  const specs: FigureSpec[] = [
    {
      key: "products",
      value: stats.data?.offer_count,
      suffix: "+",
      label: t("public.home.platformStat.products"),
      live: true,
      floor: 1,
    },
    {
      key: "companies",
      value: stats.data?.company_count,
      suffix: "+",
      label: t("public.home.platformStat.companies"),
      live: true,
      floor: 1,
    },
    {
      key: "countries",
      value: stats.data?.country_count,
      suffix: "+",
      label: t("public.home.platformStat.countries"),
      live: true,
      floor: 2,
    },
    {
      key: "requests",
      value: 1500,
      suffix: "+",
      label: t("public.home.platformStat.requests"),
      live: false,
    },
    {
      key: "deals",
      value: 10000,
      suffix: "+",
      label: t("public.home.platformStat.deals"),
      live: false,
    },
    {
      key: "satisfaction",
      value: 99.8,
      suffix: "%",
      label: t("public.home.platformStat.satisfaction"),
      live: false,
      decimals: 1,
    },
  ];

  // Apply the floor only once the data is in. `/` prefetches stats during SSR
  // (`src/ssr/prefetch.ts`), so this is normally decided before first paint —
  // but if the fetch is still open, filtering on `undefined` would drop all
  // three live rows and the grid would visibly reflow 3 → 6 when they land.
  const loading = stats.isLoading;
  const items = loading
    ? specs
    : specs.filter((spec) => !spec.live || (spec.value ?? 0) >= (spec.floor ?? 1));

  return (
    <section aria-labelledby="platform-figures" className="mt-14 lg:mt-20">
      {/* Ruled label: the band's own section divider, and the first time this
          heading has been visible rather than `sr-only`. */}
      <div data-reveal className="flex items-center gap-4">
        <span aria-hidden className="h-px flex-1 bg-border" />
        <h3
          id="platform-figures"
          className="shrink-0 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-subtle"
        >
          {t("public.home.statsHeading")}
        </h3>
        <span aria-hidden className="h-px flex-1 bg-border" />
      </div>

      {/*
        Each cell draws its own top and start hairline, and the grid is pulled
        1px up and 1px in so the outermost of those land under the container's
        own border and get clipped. Internal rules only, at every breakpoint,
        with no per-cell index arithmetic.

        The old band ruled itself with `gap-px` over a `bg-border` fill, which is
        cheaper but assumes the grid is always full. This one is not: the floor
        can drop a live figure, so 5 items in a 2-column row leaves a cell empty
        — and under that trick the empty cell painted as a solid grey block,
        which read as a rendering fault. Here an unfilled area is just the
        container's own `bg-surface`, i.e. invisible.
      */}
      <div className="mt-8 overflow-hidden rounded-md border border-border bg-surface">
        <dl className={cn("-ms-px -mt-px grid", COLUMNS[items.length] ?? COLUMNS[6])}>
          {items.map((spec, index) => (
            <Figure
              key={spec.key}
              spec={spec}
              loading={loading && spec.live}
              revealed={revealed}
              liveLabel={t("public.home.statLive")}
              delayMs={80 + index * 70}
            />
          ))}
        </dl>
      </div>
    </section>
  );
}
