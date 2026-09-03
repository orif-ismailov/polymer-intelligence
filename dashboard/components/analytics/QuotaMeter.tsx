"use client";

/**
 * How much of the Didox package is gone, and whether that is on track.
 *
 * A linear meter with the exact numbers, deliberately NOT a donut or a gauge:
 * the figure that matters here is "how many of the million are left", and a
 * proportional chart is the wrong tool the moment exact values matter more than
 * the visual fraction.
 *
 * The PACE MARKER is what makes a mid-month number readable. 400,000 of a
 * million is fine on the 20th and alarming on the 5th, and the bar alone cannot
 * say which — the marker sits where usage would be if the package were spent
 * evenly, so being left of it is ahead and right of it is behind.
 *
 * Status is never carried by colour alone: each state pairs its colour with an
 * icon and a word, because a red bar means nothing to a reader who cannot
 * distinguish it from the green one.
 *
 * No hardcoded hex — token classes only.
 */

import { AlertTriangle, CheckCircle2, TrendingUp } from "lucide-react";
import { useTranslations } from "next-intl";

interface QuotaMeterProps {
  used: number;
  quota: number;
  /** Where usage would be today at an even burn rate. */
  pace: number;
  projected: number;
}

export function QuotaMeter({ used, quota, pace, projected }: QuotaMeterProps) {
  const t = useTranslations("analytics");
  const pct = quota > 0 ? Math.min(100, (used / quota) * 100) : 0;
  const pacePct = quota > 0 ? Math.min(100, (pace / quota) * 100) : 0;
  const over = quota > 0 && projected > quota;
  const ahead = used > pace;

  // Three states, each with its own icon and its own sentence. Colour is the
  // last of the three signals rather than the only one.
  const state = over
    ? { Icon: AlertTriangle, cls: "text-urgency-high", bar: "bg-urgency-high", label: t("quota.over") }
    : ahead
      ? { Icon: TrendingUp, cls: "text-urgency-medium", bar: "bg-urgency-medium", label: t("quota.ahead") }
      : { Icon: CheckCircle2, cls: "text-accent", bar: "bg-accent", label: t("quota.onTrack") };

  return (
    <div className="rounded-lg border border-border bg-background-secondary p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-foreground">{t("quota.title")}</span>
        <span className={`flex items-center gap-1.5 text-sm font-semibold ${state.cls}`}>
          <state.Icon size={16} aria-hidden="true" />
          {state.label}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap items-end gap-x-2">
        <span className="text-[28px] font-semibold leading-none text-foreground">
          {used.toLocaleString("ru-RU")}
        </span>
        <span className="text-sm text-foreground-muted">
          {t("quota.ofQuota", { quota: quota.toLocaleString("ru-RU") })}
        </span>
      </div>

      {/* `progressbar` with the real numbers, so a screen reader gets the value
          rather than a decorative bar. */}
      <div
        className="relative mt-3 h-3 w-full overflow-hidden rounded-full bg-background-tertiary"
        role="progressbar"
        aria-valuenow={used}
        aria-valuemin={0}
        aria-valuemax={quota}
        aria-label={t("quota.title")}
      >
        <div className={`h-full rounded-full ${state.bar}`} style={{ width: `${pct}%` }} />
        {/* The pace marker. `overflow-hidden` above clips it at 100%, which is
            correct: past the end of the bar it has nothing left to mark. */}
        <div
          className="absolute inset-y-0 w-0.5 bg-foreground"
          style={{ left: `${pacePct}%` }}
          aria-hidden="true"
        />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-foreground-muted">{t("quota.pace")}</dt>
          <dd className="font-semibold text-foreground">{pace.toLocaleString("ru-RU")}</dd>
        </div>
        <div>
          <dt className="text-foreground-muted">{t("quota.projected")}</dt>
          <dd className={`font-semibold ${over ? "text-urgency-high" : "text-foreground"}`}>
            {projected.toLocaleString("ru-RU")}
          </dd>
        </div>
        <div>
          <dt className="text-foreground-muted">{t("quota.remaining")}</dt>
          <dd className="font-semibold text-foreground">
            {Math.max(0, quota - used).toLocaleString("ru-RU")}
          </dd>
        </div>
      </dl>
    </div>
  );
}
