"use client";

/**
 * SourcesList — displays the health status of all configured data sources.
 *
 * - Shows Name, Type badge, Status (enabled/disabled or Pending Phase 5 amber badge)
 * - Last Fetch, Consecutive Failures (red urgency-high if > 0)
 * - Enable/Disable toggle (PATCH /sources/{id})
 * - Test button
 * - Pending types (backend-stub adapters, last_test_ok_at=null): amber badge,
 *   disabled Test/Enable (D-05). None currently — all adapters are wired.
 *
 * No hardcoded hex. All colors via Tailwind token classes.
 */

import { useState, useEffect } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FlaskConical, ToggleLeft, ToggleRight } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

// ─── Types ─────────────────────────────────────────────────────────────────────

interface SourceHealthItem {
  id: number;
  name: string;
  adapter: string;
  kind: string;
  is_enabled: boolean;
  last_fetch_at: string | null;
  last_success_at: string | null;
  consecutive_failures: number;
  last_test_ok_at: string | null;
}

interface SourceTestResult {
  ok: boolean;
  sample_rows: Array<Record<string, unknown>>;
  error: string | null;
}

// Pending adapter types (backend-stub adapters). None currently — llm_page is
// now fully wired. Kept dormant for any future stub adapter.
const PENDING_ADAPTERS = new Set<string>();

const ADAPTER_LABELS: Record<string, string> = {
  html_table: "HTML Table",
  rss: "RSS Feed",
  telegram_channel: "Telegram Channel",
  llm_page: "LLM Page",
  uzex_offers: "UZEX Offers",
  uzex_contracts: "UZEX Contracts",
  uzex_deals: "UZEX Deals",
  cbu_rates: "CBU Rates",
};

// ─── Inline test result ────────────────────────────────────────────────────────

function TestResultBanner({ sourceId, onClose }: { sourceId: number; onClose: () => void }) {
  const t = useTranslations("sources");
  const [result, setResult] = useState<SourceTestResult | null>(null);
  const [running, setRunning] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // CR-05: replace the anti-pattern useState initializer (which fires side-effects
  // on every render in React Strict Mode double-invocation) with a proper useEffect
  // that runs once on mount and cleans up if the component unmounts before the
  // fetch resolves (prevents "state update on unmounted component" warnings).
  useEffect(() => {
    let cancelled = false;
    apiFetch<SourceTestResult>(`/sources/${sourceId}/test`, { method: "POST" })
      .then((r) => {
        if (cancelled) return;
        setResult(r);
        setRunning(false);
        if (r.ok) {
          queryClient.invalidateQueries({ queryKey: ["sources"] });
        }
      })
      .catch(() => {
        if (cancelled) return;
        setError(t("testResult.requestFailed"));
        setRunning(false);
      });
    return () => { cancelled = true; };
  }, [sourceId, queryClient, t]);

  if (running) {
    return (
      <div className="flex items-center gap-2 text-sm text-foreground-muted py-2">
        <div className="h-3 w-3 rounded-full border-2 border-accent border-t-transparent animate-spin" />
        {t("testResult.running")}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-between rounded-md border border-urgency-high/30 bg-urgency-high/10 p-2 text-sm text-urgency-high">
        {error}
        <button onClick={onClose} className="text-foreground-muted hover:text-foreground ml-2">✕</button>
      </div>
    );
  }

  if (!result) return null;

  return (
    <div className={`flex items-center justify-between rounded-md border p-2 text-sm ${result.ok ? "border-accent/30 bg-accent/10 text-accent" : "border-urgency-high/30 bg-urgency-high/10 text-urgency-high"}`}>
      <span>
        {result.ok
          ? t("testResult.passed", { count: result.sample_rows.length })
          : t("testResult.failed", { error: result.error ?? t("testResult.unknownError") })}
      </span>
      <button onClick={onClose} className="text-foreground-muted hover:text-foreground ml-2">✕</button>
    </div>
  );
}

// ─── Disable confirm dialog ────────────────────────────────────────────────────

function DisableConfirmDialog({
  open,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const t = useTranslations("sources");
  return (
    <AlertDialog open={open}>
      <AlertDialogContent className="bg-background-secondary border-border">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-foreground">{t("disableDialog.title")}</AlertDialogTitle>
          <AlertDialogDescription className="text-foreground-muted">
            {t("disableDialog.description")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel
            onClick={onCancel}
            className="border-border bg-transparent text-foreground hover:bg-background-tertiary"
          >
            {t("disableDialog.cancel")}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-status-cancelled text-white hover:bg-status-cancelled/80"
          >
            {t("disableDialog.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function SourcesList() {
  const t = useTranslations("sources");
  const queryClient = useQueryClient();
  const [testingSourceId, setTestingSourceId] = useState<number | null>(null);
  const [disableConfirmId, setDisableConfirmId] = useState<number | null>(null);

  const { data: sources = [], isLoading, error } = useQuery<SourceHealthItem[]>({
    queryKey: ["sources"],
    queryFn: () => apiFetch<SourceHealthItem[]>("/sources"),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_enabled }: { id: number; is_enabled: boolean }) =>
      apiFetch(`/sources/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_enabled }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });

  function handleToggle(source: SourceHealthItem) {
    if (source.is_enabled) {
      setDisableConfirmId(source.id);
    } else {
      // Enable: only possible if last_test_ok_at is set (backend enforces too)
      toggleMutation.mutate({ id: source.id, is_enabled: true });
    }
  }

  function confirmDisable() {
    if (disableConfirmId !== null) {
      toggleMutation.mutate({ id: disableConfirmId, is_enabled: false });
      setDisableConfirmId(null);
    }
  }

  function isPendingSource(source: SourceHealthItem): boolean {
    return PENDING_ADAPTERS.has(source.adapter) && !source.last_test_ok_at;
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-14 rounded-lg bg-background-tertiary animate-pulse" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-4 text-sm text-urgency-high">
        {t("loadError")}
      </div>
    );
  }

  if (sources.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
        <FlaskConical size={32} className="text-foreground-muted" />
        <div>
          <p className="text-sm font-semibold text-foreground">{t("empty.title")}</p>
          <p className="text-sm text-foreground-muted mt-0.5">
            {t("empty.description")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="flex flex-col gap-1">
        {/* Header */}
        <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] gap-4 px-4 py-2 text-xs font-semibold text-foreground-muted uppercase tracking-wider">
          <span>{t("columns.nameType")}</span>
          <span>{t("columns.status")}</span>
          <span>{t("columns.lastFetch")}</span>
          <span>{t("columns.failures")}</span>
          <span>{t("columns.test")}</span>
          <span>{t("columns.enable")}</span>
        </div>

        {sources.map((source) => {
          const isPending = isPendingSource(source);
          const adapterLabel = ADAPTER_LABELS[source.adapter]
            ? t(`adapterLabels.${source.adapter}`)
            : source.adapter;

          return (
            <div key={source.id} className="flex flex-col gap-1">
              <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] gap-4 items-center rounded-lg bg-background-secondary px-4 py-3 border border-border">
                {/* Name + Type badge */}
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span className="text-sm font-medium text-foreground truncate">{source.name}</span>
                  <span className="inline-flex items-center self-start rounded px-1.5 py-0.5 text-xs font-semibold bg-background-tertiary text-foreground-muted">
                    {adapterLabel}
                  </span>
                </div>

                {/* Status chip */}
                <div>
                  {isPending ? (
                    <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30 whitespace-nowrap">
                      {t("status.pending")}
                    </span>
                  ) : source.is_enabled ? (
                    <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold text-accent border border-accent/30">
                      {t("status.enabled")}
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold text-foreground-muted border border-border">
                      {t("status.disabled")}
                    </span>
                  )}
                </div>

                {/* Last Fetch */}
                <div className="text-sm text-foreground-muted">
                  {source.last_fetch_at ? (
                    <time dateTime={source.last_fetch_at} title={source.last_fetch_at}>
                      {formatTashkent(source.last_fetch_at)}
                    </time>
                  ) : (
                    <span className="text-foreground-subtle">{t("never")}</span>
                  )}
                </div>

                {/* Consecutive Failures */}
                <div className="text-sm">
                  {source.consecutive_failures > 0 ? (
                    <span className="flex items-center gap-1 text-urgency-high font-semibold">
                      <AlertTriangle size={14} aria-hidden="true" />
                      {source.consecutive_failures}
                    </span>
                  ) : (
                    <span className="text-foreground-subtle">0</span>
                  )}
                </div>

                {/* Test button */}
                <div>
                  {isPending ? (
                    <Tooltip>
                      <TooltipTrigger render={
                        <button
                          disabled
                          className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground-subtle cursor-not-allowed opacity-50"
                          aria-label={t("test.unavailableAria")}
                        >
                          {t("test.button")}
                        </button>
                      } />
                      <TooltipContent className="bg-background-tertiary text-foreground-muted text-xs border-border">
                        {t("test.availableAfterPhase5")}
                      </TooltipContent>
                    </Tooltip>
                  ) : (
                    <button
                      onClick={() => setTestingSourceId(testingSourceId === source.id ? null : source.id)}
                      className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-background-tertiary transition-colors"
                    >
                      {t("test.button")}
                    </button>
                  )}
                </div>

                {/* Enable/Disable toggle */}
                <div>
                  {isPending ? (
                    <Tooltip>
                      <TooltipTrigger render={
                        <button
                          disabled
                          className="cursor-not-allowed opacity-50"
                          aria-label={t("enable.unavailableAria")}
                        >
                          <ToggleLeft size={24} className="text-foreground-subtle" />
                        </button>
                      } />
                      <TooltipContent className="bg-background-tertiary text-foreground-muted text-xs border-border">
                        {t("test.availableAfterPhase5")}
                      </TooltipContent>
                    </Tooltip>
                  ) : (
                    <button
                      onClick={() => handleToggle(source)}
                      className="transition-colors hover:opacity-80"
                      aria-label={source.is_enabled ? t("enable.disableAria") : t("enable.enableAria")}
                      disabled={!source.is_enabled && !source.last_test_ok_at}
                      title={!source.is_enabled && !source.last_test_ok_at ? t("enable.mustTestFirst") : undefined}
                    >
                      {source.is_enabled ? (
                        <ToggleRight size={24} className="text-accent" />
                      ) : (
                        <ToggleLeft size={24} className={source.last_test_ok_at ? "text-foreground-muted" : "text-foreground-subtle opacity-40"} />
                      )}
                    </button>
                  )}
                </div>
              </div>

              {/* Inline test result */}
              {testingSourceId === source.id && (
                <div className="px-4 pb-2">
                  <TestResultBanner
                    sourceId={source.id}
                    onClose={() => setTestingSourceId(null)}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <DisableConfirmDialog
        open={disableConfirmId !== null}
        onConfirm={confirmDisable}
        onCancel={() => setDisableConfirmId(null)}
      />
    </TooltipProvider>
  );
}
