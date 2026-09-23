import type { MyRfqResponse } from "@/entities/deal";

/*
 * A .ts sibling of TenderFilters.tsx: exporting a function beside components
 * trips `react-refresh/only-export-components`, which fails lint.
 */

export type QuoteStatus = MyRfqResponse["status"];

export const QUOTE_STATUSES: readonly QuoteStatus[] = [
  "submitted",
  "accepted",
  "not_selected",
  "withdrawn",
];

/** Narrows a URL value to a quote status the API accepts; anything else is «all». */
export function parseQuoteStatus(raw: string | null): QuoteStatus | null {
  return QUOTE_STATUSES.find((status) => status === raw) ?? null;
}
