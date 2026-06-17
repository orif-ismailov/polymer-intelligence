"use client";

/**
 * AiAnalysisBlock — D-01/D-02 AI block for the request detail panel.
 *
 * D-01 placeholder contract: final-shape panels with honest placeholder text.
 *   - Match Score: progress bar empty (0%, "—" text). Phase 5 fills real data.
 *   - Demand Level: "Pending (Phase 5)".
 *   - Recommendation: "AI analysis available after Phase 5" (italic, foreground-subtle).
 *
 * D-02 REAL data: Price Analysis — computed server-side from price_points market='UZ'.
 *   - Positive delta (above market avg): text-accent
 *   - Negative delta (below market avg): text-urgency-medium
 *   - null price_analysis: "No price data available"
 *
 * RESEARCH Pattern 8 + PATTERNS.md AiAnalysisBlock section.
 * No hardcoded hex — token classes only.
 */

interface PriceAnalysis {
  target_price: number | null;
  market_avg: number | null;
  delta_pct: number | null;
  label: string | null;
}

interface AiAnalysisBlockProps {
  /** D-01: ai JSONB from the request — null fields in Phase 4. */
  ai: Record<string, unknown>;
  /** D-02: real price analysis from price_points (may be null). */
  priceAnalysis: PriceAnalysis | null;
}

export function AiAnalysisBlock({ ai, priceAnalysis }: AiAnalysisBlockProps) {
  const matchScore =
    typeof ai?.match_score === "number" ? ai.match_score : null;

  return (
    <div className="flex flex-col gap-4">
      {/* Match Score — D-01 placeholder (empty bar in Phase 4) */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-foreground-muted">Match Score</span>
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
          aria-label="Match score"
        >
          <div
            style={{
              width:
                matchScore != null ? `${Math.round(matchScore * 100)}%` : "0%",
            }}
            className="h-full bg-accent transition-all"
          />
        </div>
      </div>

      {/* Price Analysis — D-02 REAL data (not AI-dependent) */}
      <div>
        <span className="text-xs text-foreground-muted block mb-1">
          Price Analysis
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
                Market avg: {priceAnalysis.market_avg} {" "}
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
          <span className="text-sm text-foreground-subtle">
            No price data available
          </span>
        )}
      </div>

      {/* Demand Level — D-01 placeholder */}
      <div>
        <span className="text-xs text-foreground-muted block mb-1">
          Demand Level
        </span>
        <span className="text-sm text-foreground-subtle">
          Pending (Phase 5)
        </span>
      </div>

      {/* Recommendation — D-01 placeholder */}
      <div>
        <span className="text-xs text-foreground-muted block mb-1">
          Recommendation
        </span>
        <p className="text-sm text-foreground-subtle italic">
          AI analysis available after Phase 5
        </p>
      </div>
    </div>
  );
}
