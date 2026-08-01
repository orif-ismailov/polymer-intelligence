import { StrictMode } from "react";

import { dehydrate, QueryClient } from "@tanstack/react-query";
import { renderToString } from "react-dom/server";
import {
  createStaticHandler,
  createStaticRouter,
  StaticRouterProvider,
} from "react-router";

import "@/shared/i18n";

import { QueryProvider } from "@/app/providers/QueryProvider";
import { routes } from "@/app/router/routes";
import { coerceLang, i18n, SUPPORTED_LANGS } from "@/shared/i18n";
import { createHeadSink, HeadProvider, renderHeadTags } from "@/shared/seo";

import { prefetchForUrl } from "./ssr/prefetch";

export interface RenderResult {
  html: string;
  head: string;
  /** Dehydrated TanStack Query cache, inlined so the client does not refetch. */
  queryState: unknown;
  lang: string;
  status: number;
}

/**
 * Server entry: turn a URL into HTML.
 *
 * Notably absent: `AppBootstrap` and `ThemeProvider`.
 *
 * `AppBootstrap` runs the boot-time session refresh, which needs a cookie the
 * server does not have and must not borrow. Leaving it out is what makes the
 * server render deterministically anonymous — the same page for a crawler and
 * for the first paint of a logged-in browser, which is exactly what hydration
 * needs to line up.
 *
 * `ThemeProvider` is a `useEffect` that writes `data-theme` on `<html>`. There
 * is no document here, and the template already carries the dark default plus
 * the inline pre-paint script, so there is nothing for it to do.
 */
export async function render(
  url: string,
  lang: string,
  siteOrigin: string,
): Promise<RenderResult> {
  const resolvedLang = coerceLang(lang);
  await i18n.changeLanguage(resolvedLang);

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        // One attempt. A slow or failing API must not hold a page render open
        // for three backoffs; the client will retry after hydration.
        retry: false,
        staleTime: 5 * 60 * 1000,
      },
    },
  });

  await prefetchForUrl(queryClient, url, resolvedLang);

  const handler = createStaticHandler(routes);
  const context = await handler.query(new Request(new URL(url, "http://ssr.local")));

  // A redirect (or a thrown Response) comes back instead of a context. The
  // caller turns it into a real HTTP redirect rather than rendering a page.
  if (context instanceof Response) {
    return {
      html: "",
      head: "",
      queryState: null,
      lang: resolvedLang,
      status: context.status,
    };
  }

  const router = createStaticRouter(handler.dataRoutes, context);
  const sink = createHeadSink();

  // Set immediately before the SYNCHRONOUS render, with no await in between, so
  // two concurrent requests for different hosts cannot read each other's origin.
  // `publicSiteOrigin()` is called deep inside page components (canonical,
  // og:url, JSON-LD urls) and threading it through every one of them as a prop
  // would put the same value in twenty signatures.
  (globalThis as { __PUBLIC_SITE_ORIGIN__?: string }).__PUBLIC_SITE_ORIGIN__ = siteOrigin;

  const html = renderToString(
    <StrictMode>
      <HeadProvider sink={sink}>
        <QueryProvider client={queryClient}>
          <StaticRouterProvider router={router} context={context} nonce={undefined} />
        </QueryProvider>
      </HeadProvider>
    </StrictMode>,
  );

  return {
    html,
    head: renderHeadTags(sink.current),
    queryState: dehydrate(queryClient),
    lang: resolvedLang,
    status: context.statusCode ?? 200,
  };
}

export { SUPPORTED_LANGS };
