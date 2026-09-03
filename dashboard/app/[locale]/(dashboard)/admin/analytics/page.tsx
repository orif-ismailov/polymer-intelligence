"use client";

/**
 * Аналитика — what the Didox package and the AI are actually being spent on.
 *
 * Two bills, neither of which the product could see. Didox is a prepaid package
 * (a million requests a month) whose remaining balance could only be learned by
 * asking Didox; AI spend had an endpoint built for it and no screen at all.
 * Everything here reads data both rails were already journalling.
 *
 * TWO INDEPENDENT QUERIES, deliberately. They have different natural windows —
 * the package resets on a calendar month, token spend is a rolling N days — and,
 * more usefully, one failing leaves the other on screen. A page whose job is to
 * say what is happening should not go blank because half of it errored.
 *
 * `has_data` on every block, and it is load-bearing: a fresh deployment and a
 * broken integration both produce 0, and "we used none of it" reads identically
 * to "nothing has run yet" while meaning the opposite. See `EmptyPanel`.
 *
 * Gated on `appSettings:read`, matching the API.
 *
 * No hardcoded hex outside the chart components, where Recharts requires it.
 */

import { useEffect, useMemo, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  Banknote,
  Bot,
  Coins,
  Database,
  FileText,
  Gauge,
  Newspaper,
  Timer,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { EmptyPanel } from "@/components/analytics/EmptyPanel";
import { QuotaMeter } from "@/components/analytics/QuotaMeter";
import { UsageTrend } from "@/components/analytics/UsageTrend";
import { KpiCard } from "@/components/shared/KpiCard";
import { RouteGuardFallback } from "@/components/shared/RouteGuardFallback";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "@/i18n/navigation";
import { apiFetch } from "@/lib/api";

// ─── Types (mirror app/schemas/analytics.py) ───────────────────────────────────

interface DidoxOperationStat {
  operation: string;
  calls: number;
  ok: number;
  failed: number;
  p95_latency_ms: number | null;
}

interface ProviderHealth {
  provider: string;
  calls: number;
  ok: number;
  success_pct: number;
  p95_latency_ms: number | null;
}

interface DidoxAnalytics {
  month_start: string;
  days_in_month: number;
  days_elapsed: number;
  quota: number;
  cost_uzs: number;
  uzs_per_call: number;
  calls: number;
  ok: number;
  failed: number;
  not_sent: number;
  projected: number;
  pace: number;
  over_projection: boolean;
  spent_uzs: number;
  by_operation: DidoxOperationStat[];
  by_day: { day: string; calls: number }[];
  failures: { error: string; calls: number }[];
  health: ProviderHealth[];
  has_data: boolean;
}

interface AiPurposeStat {
  purpose: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  est_cost_usd: number | null;
}

interface AiModelStat extends Omit<AiPurposeStat, "purpose"> {
  model: string;
}

interface AiAnalytics {
  window_days: number;
  total_calls: number;
  total_tokens_in: number;
  total_tokens_out: number;
  est_cost_usd: number;
  by_purpose: AiPurposeStat[];
  by_model: AiModelStat[];
  daily: { day: string; purpose: string; tokens: number }[];
  degradation: {
    errors: number;
    fallbacks: number;
    deferred: number;
    rule_based_reports: number;
    last_error: string | null;
  };
  cost_per_outcome: {
    verified_companies: number;
    didox_documents: number;
    published_news: number;
    uzs_per_verified_company: number | null;
    uzs_per_document: number | null;
    tokens_per_news_article: number | null;
  };
  has_data: boolean;
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

const n = (v: number) => v.toLocaleString("ru-RU");
const dash = (v: number | null) => (v === null ? "—" : n(v));

/**
 * Respects the OS reduced-motion preference; Recharts animates by default.
 *
 * `useSyncExternalStore` rather than an effect calling `setState`: the media
 * query is external state that already exists at first paint, and reading it in
 * an effect means one render with the wrong answer — which for this hook is a
 * frame of animation shown to someone who asked for none.
 */
function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    // Server snapshot: assume motion is fine, since the client corrects it on
    // hydration and the charts do not render server-side anyway.
    () => false,
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const t = useTranslations("analytics");
  const router = useRouter();
  const { user, isAdmin, isAuthenticated, can } = useAuth();
  const reducedMotion = useReducedMotion();

  const canRead = isAdmin || can("appSettings", "read");

  useEffect(() => {
    if (isAuthenticated && user && !canRead) router.replace("/");
  }, [isAuthenticated, user, canRead, router]);

  const didox = useQuery<DidoxAnalytics>({
    queryKey: ["analytics", "didox"],
    queryFn: () => apiFetch<DidoxAnalytics>("/admin/analytics/didox"),
    enabled: canRead,
  });
  const ai = useQuery<AiAnalytics>({
    queryKey: ["analytics", "ai"],
    queryFn: () => apiFetch<AiAnalytics>("/admin/analytics/ai?days=30"),
    enabled: canRead,
  });

  const dailyBudget = useMemo(() => {
    const d = didox.data;
    return d && d.days_in_month > 0 ? d.quota / d.days_in_month : 0;
  }, [didox.data]);

  if (user && !canRead) return <RouteGuardFallback />;

  return (
    <div className="flex flex-col gap-8 p-6">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
          <Gauge size={24} className="text-foreground-muted" aria-hidden="true" />
          {t("title")}
        </h1>
        <p className="mt-1 max-w-prose text-sm text-foreground-muted">{t("subtitle")}</p>
      </header>

      {/* ── Didox ─────────────────────────────────────────────────────────── */}
      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold text-foreground">{t("didox.title")}</h2>

        {didox.isLoading && <RouteGuardFallback label={t("loading")} />}
        {didox.isError && (
          <EmptyPanel icon={AlertTriangle} title={t("loadFailed")} hint={t("loadFailedHint")} />
        )}

        {didox.data && (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard
                icon={Activity}
                label={t("didox.calls")}
                value={n(didox.data.calls)}
                delta={t("didox.ofDays", {
                  elapsed: didox.data.days_elapsed,
                  total: didox.data.days_in_month,
                })}
              />
              <KpiCard
                icon={Gauge}
                label={t("didox.projected")}
                value={n(didox.data.projected)}
                delta={didox.data.over_projection ? t("quota.over") : t("quota.onTrack")}
                deltaSentiment={didox.data.over_projection ? "negative" : "positive"}
              />
              <KpiCard
                icon={Banknote}
                label={t("didox.spent")}
                value={`${n(Math.round(didox.data.spent_uzs))} UZS`}
                delta={t("didox.ofPackage", { total: n(didox.data.cost_uzs) })}
              />
              <KpiCard
                icon={AlertTriangle}
                label={t("didox.failed")}
                value={n(didox.data.failed)}
                delta={t("didox.notSent", { count: didox.data.not_sent })}
                deltaSentiment={didox.data.failed > 0 ? "negative" : "neutral"}
              />
            </div>

            <QuotaMeter
              used={didox.data.calls}
              quota={didox.data.quota}
              pace={didox.data.pace}
              projected={didox.data.projected}
            />

            <div className="rounded-lg border border-border bg-background-secondary p-6">
              <h3 className="mb-4 text-sm font-semibold text-foreground">{t("trend.title")}</h3>
              {didox.data.by_day.length > 0 ? (
                <UsageTrend
                  data={didox.data.by_day}
                  dailyBudget={dailyBudget}
                  reducedMotion={reducedMotion}
                />
              ) : (
                <EmptyPanel
                  icon={Activity}
                  title={t("didox.emptyMonth")}
                  hint={t("didox.emptyMonthHint")}
                />
              )}
            </div>

            <div className="rounded-lg border border-border bg-background-secondary p-6">
              <h3 className="mb-4 text-sm font-semibold text-foreground">
                {t("didox.byOperation")}
              </h3>
              {didox.data.by_operation.length > 0 ? (
                <OperationTable rows={didox.data.by_operation} />
              ) : (
                <EmptyPanel icon={Database} title={t("didox.emptyMonth")} />
              )}
            </div>

            <div className="rounded-lg border border-border bg-background-secondary p-6">
              <h3 className="mb-4 text-sm font-semibold text-foreground">{t("health.title")}</h3>
              {didox.data.health.length > 0 ? (
                <HealthTable rows={didox.data.health} />
              ) : (
                <EmptyPanel icon={Timer} title={t("health.empty")} />
              )}
            </div>
          </>
        )}
      </section>

      {/* ── AI ────────────────────────────────────────────────────────────── */}
      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold text-foreground">{t("ai.title")}</h2>

        {ai.isLoading && <RouteGuardFallback label={t("loading")} />}
        {ai.isError && (
          <EmptyPanel icon={AlertTriangle} title={t("loadFailed")} hint={t("loadFailedHint")} />
        )}

        {ai.data && (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard
                icon={Bot}
                label={t("ai.calls")}
                value={n(ai.data.total_calls)}
                delta={t("ai.window", { days: ai.data.window_days })}
              />
              <KpiCard
                icon={Coins}
                label={t("ai.tokens")}
                value={n(ai.data.total_tokens_in + ai.data.total_tokens_out)}
                delta={t("ai.inOut", {
                  in: n(ai.data.total_tokens_in),
                  out: n(ai.data.total_tokens_out),
                })}
              />
              <KpiCard
                icon={Banknote}
                label={t("ai.cost")}
                value={`$${ai.data.est_cost_usd.toFixed(2)}`}
                delta={t("ai.estimate")}
              />
              <KpiCard
                icon={AlertTriangle}
                label={t("ai.degraded")}
                value={n(
                  ai.data.degradation.errors +
                    ai.data.degradation.fallbacks +
                    ai.data.degradation.deferred,
                )}
                delta={t("ai.degradedHint")}
                deltaSentiment={
                  ai.data.degradation.errors > 0 ? "negative" : "neutral"
                }
              />
            </div>

            <div className="rounded-lg border border-border bg-background-secondary p-6">
              <h3 className="mb-4 text-sm font-semibold text-foreground">{t("ai.byPurpose")}</h3>
              {ai.data.has_data ? (
                <PurposeTable rows={ai.data.by_purpose} />
              ) : (
                <EmptyPanel
                  icon={Bot}
                  title={t("ai.empty")}
                  hint={t("ai.emptyHint")}
                />
              )}
            </div>

            {ai.data.by_model.length > 0 && (
              <div className="rounded-lg border border-border bg-background-secondary p-6">
                <h3 className="mb-4 text-sm font-semibold text-foreground">{t("ai.byModel")}</h3>
                <ModelTable rows={ai.data.by_model} />
              </div>
            )}

            <DegradationPanel data={ai.data.degradation} />

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <KpiCard
                icon={BadgeCheck}
                label={t("outcome.perCompany")}
                value={
                  ai.data.cost_per_outcome.uzs_per_verified_company === null
                    ? "—"
                    : `${n(Math.round(ai.data.cost_per_outcome.uzs_per_verified_company))} UZS`
                }
                delta={t("outcome.companies", {
                  count: ai.data.cost_per_outcome.verified_companies,
                })}
              />
              <KpiCard
                icon={FileText}
                label={t("outcome.perDocument")}
                value={
                  ai.data.cost_per_outcome.uzs_per_document === null
                    ? "—"
                    : `${n(Math.round(ai.data.cost_per_outcome.uzs_per_document))} UZS`
                }
                delta={t("outcome.documents", {
                  count: ai.data.cost_per_outcome.didox_documents,
                })}
              />
              <KpiCard
                icon={Newspaper}
                label={t("outcome.perArticle")}
                value={dash(ai.data.cost_per_outcome.tokens_per_news_article)}
                delta={t("outcome.articles", {
                  count: ai.data.cost_per_outcome.published_news,
                })}
              />
            </div>
          </>
        )}
      </section>
    </div>
  );
}

// ─── Tables ────────────────────────────────────────────────────────────────────

const TH = "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted";
const TD = "px-3 py-2 text-sm text-foreground";

/**
 * Didox operations. A table rather than a bar chart: two dozen endpoints with
 * four metrics each is more than a bar can carry, and the inline bar in the
 * calls column gives the ranking a chart would have.
 */
function OperationTable({ rows }: { rows: DidoxOperationStat[] }) {
  const t = useTranslations("analytics");
  const max = Math.max(...rows.map((r) => r.calls), 1);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px]">
        <thead>
          <tr className="border-b border-border">
            <th className={TH}>{t("table.operation")}</th>
            <th className={TH}>{t("table.calls")}</th>
            <th className={TH}>{t("table.failed")}</th>
            <th className={TH}>{t("table.p95")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.operation} className="border-b border-border-subtle">
              <td className={`${TD} font-mono text-xs`}>{r.operation}</td>
              <td className={TD}>
                <div className="flex items-center gap-2">
                  <span className="tabular-nums">{n(r.calls)}</span>
                  <span
                    className="h-1.5 rounded-full bg-accent"
                    style={{ width: `${(r.calls / max) * 100}px` }}
                    aria-hidden="true"
                  />
                </div>
              </td>
              {/* Failures carry a word, not just a red number: colour alone
                  conveys nothing to a reader who cannot distinguish it. */}
              <td className={TD}>
                {r.failed > 0 ? (
                  <span className="font-semibold text-urgency-high">{n(r.failed)}</span>
                ) : (
                  <span className="text-foreground-muted">{t("table.none")}</span>
                )}
              </td>
              <td className={`${TD} tabular-nums`}>
                {r.p95_latency_ms === null ? "—" : `${n(r.p95_latency_ms)} ms`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HealthTable({ rows }: { rows: ProviderHealth[] }) {
  const t = useTranslations("analytics");
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px]">
        <thead>
          <tr className="border-b border-border">
            <th className={TH}>{t("table.provider")}</th>
            <th className={TH}>{t("table.calls")}</th>
            <th className={TH}>{t("table.success")}</th>
            <th className={TH}>{t("table.p95")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.provider} className="border-b border-border-subtle">
              <td className={`${TD} font-mono text-xs`}>{r.provider}</td>
              <td className={`${TD} tabular-nums`}>{n(r.calls)}</td>
              <td className={TD}>
                <span
                  className={
                    r.success_pct >= 99
                      ? "text-accent"
                      : r.success_pct >= 90
                        ? "text-urgency-medium"
                        : "text-urgency-high"
                  }
                >
                  {r.success_pct}%
                </span>
              </td>
              <td className={`${TD} tabular-nums`}>
                {r.p95_latency_ms === null ? "—" : `${n(r.p95_latency_ms)} ms`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PurposeTable({ rows }: { rows: AiPurposeStat[] }) {
  const t = useTranslations("analytics");
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px]">
        <thead>
          <tr className="border-b border-border">
            <th className={TH}>{t("table.purpose")}</th>
            <th className={TH}>{t("table.calls")}</th>
            <th className={TH}>{t("table.tokensIn")}</th>
            <th className={TH}>{t("table.tokensOut")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.purpose} className="border-b border-border-subtle">
              <td className={TD}>{t(`purpose.${r.purpose}`)}</td>
              <td className={`${TD} tabular-nums`}>{n(r.calls)}</td>
              <td className={`${TD} tabular-nums`}>{n(r.tokens_in)}</td>
              <td className={`${TD} tabular-nums`}>{n(r.tokens_out)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ModelTable({ rows }: { rows: AiModelStat[] }) {
  const t = useTranslations("analytics");
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px]">
        <thead>
          <tr className="border-b border-border">
            <th className={TH}>{t("table.model")}</th>
            <th className={TH}>{t("table.calls")}</th>
            <th className={TH}>{t("table.tokens")}</th>
            <th className={TH}>{t("table.cost")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.model} className="border-b border-border-subtle">
              <td className={`${TD} font-mono text-xs`}>{r.model}</td>
              <td className={`${TD} tabular-nums`}>{n(r.calls)}</td>
              <td className={`${TD} tabular-nums`}>{n(r.tokens_in + r.tokens_out)}</td>
              <td className={`${TD} tabular-nums`}>
                {r.est_cost_usd === null ? "—" : `$${r.est_cost_usd.toFixed(4)}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Where the AI quietly did not work.
 *
 * Every path counted here is silent by design — a failed extraction becomes a
 * rule-based one, an exhausted budget defers the item, a failed digest falls
 * back to a deterministic summary. Each is correct behaviour, and together they
 * mean a month of the AI being off by a bad key looks exactly like a month of it
 * working. This panel is the only place that difference shows.
 */
function DegradationPanel({
  data,
}: {
  data: AiAnalytics["degradation"];
}) {
  const t = useTranslations("analytics");
  const items = [
    { key: "errors", value: data.errors },
    { key: "fallbacks", value: data.fallbacks },
    { key: "deferred", value: data.deferred },
    { key: "ruleBasedReports", value: data.rule_based_reports },
  ];
  return (
    <div className="rounded-lg border border-border bg-background-secondary p-6">
      <h3 className="mb-4 text-sm font-semibold text-foreground">{t("degradation.title")}</h3>
      <p className="mb-4 max-w-prose text-xs text-foreground-muted">{t("degradation.hint")}</p>
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {items.map((i) => (
          <div key={i.key}>
            <dt className="text-xs text-foreground-muted">{t(`degradation.${i.key}`)}</dt>
            <dd
              className={`text-lg font-semibold ${
                i.value > 0 ? "text-urgency-medium" : "text-foreground"
              }`}
            >
              {n(i.value)}
            </dd>
          </div>
        ))}
      </dl>
      {data.last_error && (
        <p className="mt-4 break-words rounded-md border border-border-subtle bg-background p-3 font-mono text-xs text-urgency-high">
          {data.last_error}
        </p>
      )}
    </div>
  );
}
