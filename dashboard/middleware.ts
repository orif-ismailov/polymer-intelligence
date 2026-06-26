import createMiddleware from "next-intl/middleware";

import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  // Run on every path EXCEPT: /api (proxied to the backend), Next internals,
  // and anything with a file extension (static assets). Without excluding /api
  // the locale middleware would rewrite the backend proxy paths.
  matcher: "/((?!api|_next|_vercel|.*\\..*).*)",
};
