import createMiddleware from "next-intl/middleware";
import { NextResponse, type NextRequest } from "next/server";

import { routing } from "./i18n/routing";

const intlMiddleware = createMiddleware(routing);

/**
 * A first path segment that is SHAPED like a language tag — `en`, `xx`, `de-DE`.
 *
 * Deliberately narrow. Every top-level route this app has (`login`, `signals`,
 * `moderation`, `admin`, …) is longer than two letters, so nothing real can be
 * caught by it; widening this to "any unknown segment" would send a genuine typo
 * like `/ru/singals` through the same rewrite and hide it.
 */
const LOCALE_SHAPED = /^[a-z]{2}(?:-[a-zA-Z]{2,4})?$/;

/**
 * Locale routing, plus the one thing next-intl does not do on its own.
 *
 * Given a path that ALREADY begins with an unsupported language tag, next-intl
 * prefixes the default locale rather than recognising it as a language request
 * at all: `/en/login` became `/ru/en/login`, a route that does not exist, so
 * every link built with a language this panel does not ship landed on Next's
 * bare 404 (IMEX-22). The panel serves ru, uz, tr, fa and zh — and `/en/…` is
 * exactly the link a person or a tool is most likely to guess.
 *
 * So an unsupported-but-locale-shaped prefix is treated as what it plainly is: a
 * request for THIS page in a language we do not have. It redirects to the same
 * page in the default locale, SWAPPING the segment rather than stacking another
 * one in front of it.
 */
export default function middleware(request: NextRequest) {
  const [, first = "", ...rest] = request.nextUrl.pathname.split("/");
  const supported = routing.locales as readonly string[];

  if (first && LOCALE_SHAPED.test(first) && !supported.includes(first)) {
    const url = request.nextUrl.clone();
    const tail = rest.join("/");
    url.pathname = `/${routing.defaultLocale}${tail ? `/${tail}` : ""}`;
    return NextResponse.redirect(url);
  }

  return intlMiddleware(request);
}

export const config = {
  // Run on every path EXCEPT: /api (proxied to the backend), Next internals,
  // and anything with a file extension (static assets). Without excluding /api
  // the locale middleware would rewrite the backend proxy paths.
  matcher: "/((?!api|_next|_vercel|.*\\..*).*)",
};
