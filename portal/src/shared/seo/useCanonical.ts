import { useMemo } from "react";

import { buildCanonical } from "./headContext";

/**
 * Memoized canonical + `hreflang` alternates for the current page.
 *
 * A thin hook over `buildCanonical` so the object identity is stable: `<Seo/>`
 * keys its effect on a JSON serialization of its props, and a fresh
 * `alternates` object every render would make that key change every render.
 */
export function useCanonical(
  origin: string,
  pathname: string,
  langs: readonly string[],
  currentLang: string,
): { canonical: string; alternates: Record<string, string> } {
  return useMemo(
    () => buildCanonical(origin, pathname, langs, currentLang),
    [origin, pathname, langs, currentLang],
  );
}
