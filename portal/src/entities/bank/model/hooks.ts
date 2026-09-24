import { useQuery } from "@tanstack/react-query";

import { bankApi, bankKeys } from "./api";
import type { BankBranch } from "./types";

/** The MFO is exactly five digits — the same rule the bank step validates by. */
function isLookupableMfo(mfo: string): boolean {
  return /^\d{5}$/.test(mfo);
}

/**
 * The bank behind an MFO, for prefilling «Название банка».
 *
 * `enabled` guards two things at once: a half-typed MFO (no request until the
 * fifth digit) and SSR — an unguarded query fires from Node during a server
 * render, which is how `useCompanies()` was quietly calling the API on every
 * public page.
 *
 * `retry: false` because the only failure worth distinguishing is 404, and
 * retrying it cannot change the answer. A miss leaves the field alone.
 */
export function useBankByMfo(mfo: string, enabled = true) {
  const normalized = mfo.trim();
  return useQuery<BankBranch>({
    queryKey: bankKeys.byMfo(normalized),
    queryFn: () => bankApi.byMfo(normalized),
    enabled: enabled && isLookupableMfo(normalized),
    retry: false,
    // The register changes a few times a year; there is no reason to ask twice
    // in a session for the same five digits.
    staleTime: 60 * 60 * 1000,
  });
}
