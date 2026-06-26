"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";

import { apiFetch } from "@/lib/api";

/**
 * AiAnalysisBlock — request-detail AI panel.
 *
 * Phase 5: match_score / demand_level / recommendation are computed by the LLM
 * (request_analysis_service) and echoed from request.ai. When a request has not been
 * analysed yet (ai empty), the fields fall back to honest placeholders and a "Run AI
 * analysis" button triggers POST /requests/{id}/analyze (new requests are analysed
 * automatically on submit). Price Analysis is real, non-AI data from price_points.
 *
 * No hardcoded hex — token classes only.
 */

interface PriceAnalysis {
  target_price: number | null;
  market_avg: number | null;
  delta_pct: number | null;
  label: string | null;
}

interface AiAnalysisBlockProps {
  /** Request id — needed to (re)trigger analysis. */
  requestId: number;
  /** ai JSONB from the request (match_score/demand_level/recommendation when analysed). */
  ai: Record<string, unknown>;
  /** Real price analysis from price_points (may be null). */
  priceAnalysis: PriceAnalysis | null;
}

const DEMAND_CLASSES: Record<string, string> = {
  low: "text-urgency-low",
  medium: "text-urgency-medium",
  high: "text-urgency-high",
};

export function AiAnalysisBlock({ requestId, ai, priceAnalysis }: AiAnalysisBlockProps) {
  const t = useTranslations("requests");
  const queryClient = useQueryClient();

  const matchScore = typeof ai?.match_score === "number" ? ai.match_score : null;
  const demandLevel =
    typeof ai?.demand_level === "string" ? (ai.demand_level as string) : null;
  const recommendation =
    typeof ai?.recommendation === "string" && ai.recommendation.trim()
      ? (ai.recommendation as string)
      : null;
  const hasAnalysis = matchScore != null || demandLevel != null || recommendation != null;

  const analysis = useMutation({
    mutationFn: () => apiFetch(`/requests/${requestId}/analyze`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["request", String(requestId)] });
    },
  });

  function demandLabel(level: string): string {
    if (level === "low") return t("demandLevelLow");
    if (level === "medium") return t("demandLevelMedium");
    if (level === "high") return t("demandLevelHigh");
    return t("demandLevelPending");
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Match Score */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-foreground-muted">{t("matchScore")}</span>
          <span className="text-xs font-mono text-foreground-muted">
            {matchScore != null ? `${Math.round(matchScore * 100)}%` : "—"}
          </span>
        </div>
        <div
          className="h-2 w-full rounded-full bg-background-tertiary overflow-hidden"
          role="progressbar"
          aria-valuenow={matchScore != null ? Math.round(matchScore * 100) : 0}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={t("matchScore")}
        >
          <div
            style={{
              width: matchScore != null ? `${Math.round(matchScore * 100)}%` : "0%",
            }}
            className="h-full bg-accent transition-all"
          />
        </div>
      </div>

      {/* Price Analysis — real data (not AI-dependent) */}
      <div>
        <span className="text-xs text-foreground-muted block mb-1">
          {t("priceAnalysis")}
        </span>
        {priceAnalysis != null ? (
          <div className="flex flex-col gap-1">
            <span
              className={`text-sm font-semibold ${
                (priceAnalysis.delta_pct ?? 0) >= 0
                  ? "text-accent"
                  : "text-urgency-medium"
              }`}
            >
              {priceAnalysis.label ?? "—"}
            </span>
            {priceAnalysis.market_avg != null && (
              <span className="text-xs text-foreground-muted">
                {t("marketAvg")}: {priceAnalysis.market_avg} {" "}
                {priceAnalysis.delta_pct != null && (
                  <span
                    className={
                      priceAnalysis.delta_pct >= 0
                        ? "text-accent"
                        : "text-urgency-medium"
                    }
                  >
                    ({priceAnalysis.delta_pct > 0 ? "+" : ""}
                    {priceAnalysis.delta_pct.toFixed(1)}%)
                  </span>
                )}
              </span>
            )}
          </div>
        ) : (
          <span className="text-sm text-foreground-subtle">{t("noPriceData")}</span>
        )}
      </div>

      {/* Demand Level — AI */}
      <div>
        <span className="text-xs text-foreground-muted block mb-1">
          {t("demandLevel")}
        </span>
        {demandLevel != null ? (
          <span
            className={`text-sm font-semibold ${
              DEMAND_CLASSES[demandLevel] ?? "text-foreground"
            }`}
          >
            {demandLabel(demandLevel)}
          </span>
        ) : (
          <span className="text-sm text-foreground-subtle">{t("demandLevelPending")}</span>
        )}
      </div>

      {/* Recommendation — AI */}
      <div>
        <span className="text-xs text-foreground-muted block mb-1">
          {t("recommendation")}
        </span>
        {recommendation != null ? (
          <p className="text-sm text-foreground">{recommendation}</p>
        ) : (
          <p className="text-sm text-foreground-subtle italic">
            {t("recommendationPending")}
          </p>
        )}
      </div>

      {/* Run / re-run analysis */}
      <div className="flex flex-col gap-1.5">
        <button
          type="button"
          onClick={() => analysis.mutate()}
          disabled={analysis.isPending}
          className="inline-flex items-center justify-center gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {analysis.isPending ? (
            <Loader2 size={15} className="animate-spin" aria-hidden="true" />
          ) : (
            <Sparkles size={15} aria-hidden="true" />
          )}
          {analysis.isPending
            ? t("analyzing")
            : hasAnalysis
              ? t("rerunAnalysis")
              : t("runAnalysis")}
        </button>
        {analysis.isError && (
          <span role="alert" className="text-xs text-urgency-high">
            {t("analysisFailed")}
          </span>
        )}
      </div>
    </div>
  );
}
