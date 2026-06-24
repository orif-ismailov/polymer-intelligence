/**
 * useDashboardSummary — fetches GET /api/v1/dashboard/summary once for the
 * Dashboard home page (KPIs + top requests/offers + AI signals).
 *
 * Fetched ONCE here and sliced down to the panels to avoid double-fetching.
 * staleTime aligns with the SSE polling fallback interval (DEC-realtime-sse-not-websocket).
 *
 * Decimal fields (volume, target_price, price) arrive as JSON strings from the
 * backend — types reflect that exactly; format at the display layer.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";

export interface DashboardKpis {
  total_buyers: number;
  total_sellers: number;
  active_requests: number;
  hot_leads: number;
  alert_rules: number;
}

export interface DashboardTopRequest {
  id: number;
  number: string;
  product_id: number | null;
  product: string | null;
  grade_text: string | null;
  volume: string | null;
  target_price: string | null;
  currency: string | null;
  urgency: string | null;
  status: string;
  created_at: string;
}

export interface DashboardTopOffer {
  id: number;
  kind: string;
  product_id: number | null;
  product: string | null;
  grade_text: string | null;
  volume: string | null;
  price: string | null;
  currency: string | null;
  region: string | null;
  event_at: string;
}

export interface DashboardAiSignal {
  id: number;
  kind: string;
  product_id: number | null;
  product: string | null;
  grade_text: string | null;
  classification: string | null;
  lead_score: number | null;
  needs_review: boolean;
  event_at: string;
}

export interface DashboardSummary {
  kpis: DashboardKpis;
  top_requests: DashboardTopRequest[];
  top_offers: DashboardTopOffer[];
  ai_signals: DashboardAiSignal[];
}

export const DASHBOARD_SUMMARY_QUERY_KEY = ["dashboard-summary"] as const;

export function useDashboardSummary(): UseQueryResult<DashboardSummary> {
  return useQuery<DashboardSummary>({
    queryKey: DASHBOARD_SUMMARY_QUERY_KEY,
    queryFn: () => apiFetch<DashboardSummary>("/dashboard/summary"),
    // KPIs/top lists tolerate brief staleness; matches the feed polling cadence.
    staleTime: 60_000,
  });
}
