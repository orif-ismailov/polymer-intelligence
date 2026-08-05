import { useLocation } from "react-router-dom";

import { CABINET_BASE, isCabinetPath } from "@/shared/config";

/**
 * `"/cabinet"` when rendered inside the cabinet, `""` on the storefront.
 *
 * A handful of pages are mounted in BOTH tiers because they read the same either
 * way — the news reader, the price table, the three read-only directories. Only
 * the chrome differs, so the component is shared, and its internal links have to
 * follow whichever tier the visitor is actually in. Hardcoding `/news/123` would
 * throw a signed-in reader back onto the storefront, where the guard would
 * immediately bounce them to `/cabinet/news/123` — right destination, two
 * navigations and a flash of the wrong shell.
 *
 * Prefer this over relative `to=".."` links in those components: relative
 * resolution in React Router is against the matched ROUTE, not the URL, which is
 * a different thing on a route with params and reads as a bug when it surprises
 * you.
 */
export function useTierBase(): string {
  return isCabinetPath(useLocation().pathname) ? CABINET_BASE : "";
}
