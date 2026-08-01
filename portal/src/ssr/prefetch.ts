import type { QueryClient } from "@tanstack/react-query";

import {
  fetchPublicCategories,
  fetchPublicCompany,
  fetchPublicDirectory,
  fetchPublicNews,
  fetchPublicOffer,
  fetchPublicOffers,
  fetchPublicPrices,
  fetchPublicStats,
  publicKeys,
  type PublicOfferFilters,
} from "@/entities/public";
import { directoryBySlug } from "@/shared/config";

/**
 * What each public URL needs loaded before it can be rendered as HTML.
 *
 * This is an explicit map rather than route loaders, and the reason is the
 * hybrid tier: the SAME route component serves anonymous and signed-in
 * visitors, so a react-router loader would have to run for both and would have
 * no session to run with. Prefetching by URL keeps the server's job narrow — it
 * fills the query cache for the anonymous view and nothing else.
 *
 * A page NOT listed here still renders; it just renders its loading state and
 * fetches after hydration. That is the correct outcome for anything behind the
 * login, which is why the cabinet is deliberately absent.
 *
 * Every prefetch is wrapped so one failing endpoint degrades that section to its
 * client-side loading state instead of failing the whole page. A storefront that
 * 500s because the price rail is down is worse than one that renders without it.
 */

const PAGE_SIZE = 24;

async function settle(label: string, work: Promise<unknown>): Promise<void> {
  try {
    await work;
  } catch (err) {
    // Logged, not thrown. The client will retry this query on mount.
    console.warn(`[ssr] prefetch failed for ${label}:`, (err as Error).message);
  }
}

export async function prefetchForUrl(
  queryClient: QueryClient,
  url: string,
  lang: string,
): Promise<void> {
  const { pathname, searchParams } = new URL(url, "http://ssr.local");
  const segments = pathname.replace(/^\/+|\/+$/g, "").split("/").filter(Boolean);

  const prefetch = <T,>(key: readonly unknown[], fn: () => Promise<T>): Promise<unknown> =>
    queryClient.prefetchQuery({ queryKey: key, queryFn: fn });

  // ── / ─────────────────────────────────────────────────────────────────────
  if (segments.length === 0) {
    await Promise.all([
      settle("stats", prefetch(publicKeys.stats(), fetchPublicStats)),
      settle(
        "categories",
        prefetch(publicKeys.categories(lang), () => fetchPublicCategories(lang)),
      ),
      settle(
        "featured",
        prefetch(publicKeys.offers({}, 0, 4), () => fetchPublicOffers({}, 0, 4)),
      ),
      settle(
        "prices",
        prefetch(publicKeys.prices(lang, 6), () => fetchPublicPrices(lang, 6)),
      ),
      settle("news", prefetch(publicKeys.news(lang, 3), () => fetchPublicNews(lang, 3))),
      settle(
        "manufacturers",
        prefetch(publicKeys.directory("manufacturers", "", "", 0, 6), () =>
          fetchPublicDirectory("manufacturers", "", "", 0, 6),
        ),
      ),
    ]);
    return;
  }

  // ── /market and /market/:id ───────────────────────────────────────────────
  if (segments[0] === "market") {
    if (segments.length === 1) {
      const productIdRaw = searchParams.get("product_id");
      const availability = searchParams.get("availability");
      // Annotated, so this object stays the same shape the page builds. Without
      // it `availability` widens to `string` and the two would silently produce
      // different query keys, which is a cache miss and a double fetch on every
      // filtered page load.
      const filters: PublicOfferFilters = {
        q: searchParams.get("q") || undefined,
        product_id: productIdRaw ? Number(productIdRaw) : undefined,
        availability:
          availability === "in_stock" || availability === "on_order" ? availability : undefined,
        country: (searchParams.get("country") || "").toUpperCase() || undefined,
        lab_verified: searchParams.get("lab_verified") === "1" || undefined,
        has_lab_passport: searchParams.get("has_lab_passport") === "1" || undefined,
      };
      const offset = Math.max(0, Number(searchParams.get("offset") ?? 0) || 0);
      await Promise.all([
        settle(
          "categories",
          prefetch(publicKeys.categories(lang), () => fetchPublicCategories(lang)),
        ),
        settle(
          "offers",
          prefetch(publicKeys.offers(filters, offset, PAGE_SIZE), () =>
            fetchPublicOffers(filters, offset, PAGE_SIZE),
          ),
        ),
      ]);
      return;
    }
    const offerSegment = segments[1];
    if (segments.length === 2 && offerSegment && /^\d+$/.test(offerSegment)) {
      const offerId = Number(offerSegment);
      await settle(
        `offer:${offerId}`,
        prefetch(publicKeys.offer(offerId), () => fetchPublicOffer(offerId)),
      );
      return;
    }
    return;
  }

  // ── /prices ───────────────────────────────────────────────────────────────
  if (segments[0] === "prices" && segments.length === 1) {
    await settle(
      "prices",
      prefetch(publicKeys.prices(lang, 40), () => fetchPublicPrices(lang, 40)),
    );
    return;
  }

  // ── /news ─────────────────────────────────────────────────────────────────
  // The news reader is the cabinet's component and reads the authenticated
  // endpoint, so there is nothing anonymous to prefetch for it yet. The route is
  // still server-rendered (shell + head), which is what the canonical needs.
  if (segments[0] === "news") return;

  // ── /{directory} and /{directory}/{id} ────────────────────────────────────
  const directory = directoryBySlug(segments[0]);
  if (directory) {
    if (segments.length === 1) {
      const q = searchParams.get("q") ?? "";
      const country = (searchParams.get("country") ?? "").toUpperCase();
      const offset = Math.max(0, Number(searchParams.get("offset") ?? 0) || 0);
      await settle(
        `directory:${directory.slug}`,
        prefetch(publicKeys.directory(directory.slug, q, country, offset, PAGE_SIZE), () =>
          fetchPublicDirectory(directory.slug, q, country, offset, PAGE_SIZE),
        ),
      );
      return;
    }
    const companySegment = segments[1];
    if (segments.length === 2 && companySegment && /^\d+$/.test(companySegment)) {
      const companyId = Number(companySegment);
      await settle(
        `company:${directory.slug}/${companyId}`,
        prefetch(publicKeys.company(directory.slug, companyId), () =>
          fetchPublicCompany(directory.slug, companyId),
        ),
      );
    }
  }
}

