"use client";

/**
 * AiMarketSignalsPanel — renders real AI market signals from the dashboard summary.
 *
 * Signals are fetched ONCE on the Dashboard home page and passed in as a prop
 * (avoids double-fetching the summary endpoint). Each row shows product / grade,
 * a HOT / MEDIUM / LOW classification badge, the lead score, and a relative time.
 *
 * States: loading spinner, graceful empty state, and the populated list.
 * No hardcoded hex — token classes only.
 */

import { Bot } from "lucide-react";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { relativeTime } from "@/lib/tz";
import type { DashboardAiSignal } from "@/hooks/useDashboardSummary";

const CLASSIFICATION_CLASSES: Record<string, string> = {
  HOT: "text-urgency-high border-urgency-high",
  MEDIUM: "text-urgency-medium border-urgency-medium",
  LOW: "text-urgency-low border-urgency-low",
};

function ClassificationBadge({ classification }: { classification: string | null }) {
  if (!classification) {
    return <span className="text-sm text-foreground-subtle">—</span>;
  }
  const colorClasses =
    CLASSIFICATION_CLASSES[classification] ??
    "text-foreground-muted border-foreground-muted";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${colorClasses}`}
    >
      {classification}
    </span>
  );
}

interface AiMarketSignalsPanelProps {
  signals?: DashboardAiSignal[];
  isLoading?: boolean;
  className?: string;
}

export function AiMarketSignalsPanel({
  signals,
  isLoading = false,
  className = "",
}: AiMarketSignalsPanelProps) {
  const t = useTranslations("home");
  return (
    <div
      className={`rounded-lg bg-background-secondary border border-border ${className}`}
      aria-label={t("aiMarketSignalsAria")}
    >
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-2">
          <Bot size={20} className="text-foreground-muted" aria-hidden="true" />
          <h2 className="text-base font-semibold text-foreground">{t("aiMarketSignals")}</h2>
        </div>
        <Link
          href="/signals?needs_review=true"
          className="text-sm text-accent hover:text-accent-light transition-colors"
        >
          {t("viewAll")}
        </Link>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          <span className="ml-3 text-sm text-foreground-muted">{t("loadingSignals")}</span>
        </div>
      ) : !signals?.length ? (
        <div className="flex flex-col items-center justify-center gap-2 py-10">
          <Bot size={28} className="text-foreground-muted" aria-hidden="true" />
          <p className="text-sm text-foreground-muted">{t("noSignals")}</p>
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {signals.map((signal) => (
            <li key={signal.id} className="flex items-center gap-4 px-6 py-4">
              <Bot
                size={20}
                className="flex-shrink-0 text-foreground-muted"
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-foreground">
                  {signal.product ?? "—"}
                  {signal.grade_text ? (
                    <span className="font-normal text-foreground-muted">
                      {" · "}
                      {signal.grade_text}
                    </span>
                  ) : null}
                </p>
                <time
                  dateTime={signal.event_at}
                  title={signal.event_at}
                  className="text-xs text-foreground-muted"
                >
                  {relativeTime(signal.event_at)}
                </time>
              </div>
              <div className="flex items-center gap-4">
                <span className="whitespace-nowrap text-sm font-mono text-foreground">
                  {signal.lead_score != null
                    ? t("leadScore", { score: signal.lead_score })
                    : "—"}
                </span>
                <ClassificationBadge classification={signal.classification} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
