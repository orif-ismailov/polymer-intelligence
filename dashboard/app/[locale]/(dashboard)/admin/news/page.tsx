"use client";

/**
 * News Admin (/admin/news) — Phase 8d/8e control panel.
 *
 * Three surfaces backed by /api/v1/admin:
 *  - News-ops stats (GET /admin/news/stats) + Run-Parser / Generate-Report actions.
 *  - Runtime settings (GET/PUT /admin/settings) — admin only; toggles + text inputs.
 *  - Approval queue (GET /admin/news/pending, POST /{id}/approve|reject) — analyst+.
 */

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Play, RefreshCw, SlidersHorizontal, X } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

interface SettingItem {
  key: string;
  type: "bool" | "str";
  label: string;
  value: boolean | string;
  default: boolean | string;
  is_overridden: boolean;
}

interface NewsStats {
  total_sources: number;
  active_sources: number;
  failed_sources: number;
  last_scan: string | null;
  last_published_report: string | null;
  pending_ai_analysis: number;
  today_published_news: number;
  ai_enabled: boolean;
  ai_status: string;
}

interface PendingNewsItem {
  id: number;
  headline: string;
  category: string | null;
  importance: string | null;
  summary: string | null;
  country: string | null;
  source_name: string | null;
  published_at: string | null;
}

function fmtDateTime(iso: string | null, fallback: string): string {
  if (!iso) return fallback;
  return iso.replace("T", " ").slice(0, 16);
}

export default function NewsAdminPage() {
  const t = useTranslations("newsAdmin");
  const qc = useQueryClient();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  // ── Queries ──────────────────────────────────────────────────────────────
  const stats = useQuery<NewsStats>({
    queryKey: ["news-stats"],
    queryFn: () => apiFetch<NewsStats>("/admin/news/stats"),
  });
  const pending = useQuery<PendingNewsItem[]>({
    queryKey: ["news-pending"],
    queryFn: () => apiFetch<PendingNewsItem[]>("/admin/news/pending"),
  });
  const settings = useQuery<SettingItem[]>({
    queryKey: ["admin-settings"],
    queryFn: () => apiFetch<SettingItem[]>("/admin/settings"),
    enabled: isAdmin, // GET /admin/settings is admin-only; don't 401 analysts
  });

  // ── Local edit buffer for settings ──────────────────────────────────────
  const [edits, setEdits] = useState<Record<string, boolean | string>>({});
  const valueOf = (s: SettingItem): boolean | string =>
    s.key in edits ? edits[s.key]! : s.value;
  const dirty = useMemo(() => Object.keys(edits).length > 0, [edits]);

  // ── Mutations ────────────────────────────────────────────────────────────
  const invalidate = (keys: string[]) =>
    keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));

  const saveSettings = useMutation({
    mutationFn: () => apiFetch("/admin/settings", { method: "PUT", body: JSON.stringify(edits) }),
    onSuccess: () => {
      setEdits({});
      invalidate(["admin-settings", "news-stats"]);
    },
  });
  const runParser = useMutation({
    mutationFn: () => apiFetch("/admin/news/run-parser", { method: "POST" }),
    onSuccess: () => invalidate(["news-stats"]),
  });
  const generateReport = useMutation({
    mutationFn: () => apiFetch("/admin/reports/generate", { method: "POST" }),
    onSuccess: () => invalidate(["news-stats"]),
  });
  const decide = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "approve" | "reject" }) =>
      apiFetch(`/admin/news/${id}/${action}`, { method: "POST" }),
    onSuccess: () => invalidate(["news-pending", "news-stats"]),
  });

  const s = stats.data;

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header + actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <SlidersHorizontal size={24} className="text-foreground-muted" aria-hidden="true" />
          <div>
            <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
            <p className="text-sm text-foreground-muted mt-1">{t("subtitle")}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={runParser.isPending || !isAdmin}
            onClick={() => runParser.mutate()}
            className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary disabled:opacity-50"
          >
            <RefreshCw size={15} className={runParser.isPending ? "animate-spin" : ""} />
            {t("actions.runParser")}
          </button>
          <button
            type="button"
            disabled={generateReport.isPending}
            onClick={() => generateReport.mutate()}
            className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
          >
            <Play size={15} />
            {t("actions.generateReport")}
          </button>
        </div>
      </div>

      {/* ── Stats grid ─────────────────────────────────────────────────────── */}
      {stats.isError && <p className="text-sm text-red-400">{t("error")}</p>}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label={t("stats.totalSources")} value={s ? String(s.total_sources) : "…"} />
        <StatCard label={t("stats.activeSources")} value={s ? String(s.active_sources) : "…"} />
        <StatCard
          label={t("stats.failedSources")}
          value={s ? String(s.failed_sources) : "…"}
          tone={s && s.failed_sources > 0 ? "danger" : "default"}
        />
        <StatCard label={t("stats.pendingAi")} value={s ? String(s.pending_ai_analysis) : "…"} />
        <StatCard label={t("stats.todayNews")} value={s ? String(s.today_published_news) : "…"} />
        <StatCard label={t("stats.lastScan")} value={s ? fmtDateTime(s.last_scan, t("stats.never")) : "…"} />
        <StatCard
          label={t("stats.lastPublished")}
          value={s ? fmtDateTime(s.last_published_report, t("stats.never")) : "…"}
        />
        <StatCard
          label={t("stats.aiStatus")}
          value={s ? t(s.ai_enabled ? "stats.on" : "stats.off") : "…"}
          tone={s ? (s.ai_enabled ? "accent" : "muted") : "default"}
        />
      </div>

      {/* ── Runtime settings (admin only) ──────────────────────────────────── */}
      {isAdmin && (
        <section className="rounded-lg border border-border bg-background-secondary p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-base font-semibold text-foreground">{t("settings.title")}</h2>
            <button
              type="button"
              disabled={!dirty || saveSettings.isPending}
              onClick={() => saveSettings.mutate()}
              className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-40"
            >
              {saveSettings.isPending ? "…" : t("actions.save")}
            </button>
          </div>
          {settings.isError && <p className="text-sm text-red-400">{t("error")}</p>}
          <ul className="flex flex-col divide-y divide-border">
            {settings.data?.map((item) => (
              <li key={item.key} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{item.label}</p>
                  <p className="truncate text-xs text-foreground-muted">
                    {item.key}
                    {item.is_overridden || item.key in edits ? "" : ` · ${t("settings.default")}`}
                  </p>
                </div>
                {item.type === "bool" ? (
                  <Toggle
                    on={Boolean(valueOf(item))}
                    onChange={(v) => setEdits((e) => ({ ...e, [item.key]: v }))}
                  />
                ) : (
                  <input
                    value={String(valueOf(item))}
                    onChange={(e) => setEdits((prev) => ({ ...prev, [item.key]: e.target.value }))}
                    className="w-56 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
                  />
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── Approval queue ─────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-background-secondary p-4">
        <h2 className="mb-3 text-base font-semibold text-foreground">
          {t("approval.title")}
          {pending.data && pending.data.length > 0 && (
            <span className="ms-2 rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-400">
              {pending.data.length}
            </span>
          )}
        </h2>
        {pending.isLoading && <p className="text-sm text-foreground-muted">…</p>}
        {pending.data && pending.data.length === 0 && (
          <p className="text-sm text-foreground-muted">{t("approval.empty")}</p>
        )}
        <div className="flex flex-col gap-3">
          {pending.data?.map((a) => (
            <div
              key={a.id}
              className="flex items-start justify-between gap-4 rounded-md border border-border bg-background p-3"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">{a.headline}</p>
                {a.summary && (
                  <p className="mt-1 line-clamp-2 text-xs text-foreground-muted">{a.summary}</p>
                )}
                <p className="mt-1 text-xs text-foreground-muted">
                  {[a.source_name, a.category, a.country, a.published_at?.slice(0, 10)]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <div className="flex flex-shrink-0 gap-2">
                <button
                  type="button"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ id: a.id, action: "approve" })}
                  className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
                >
                  <Check size={15} /> {t("approval.approve")}
                </button>
                <button
                  type="button"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ id: a.id, action: "reject" })}
                  className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-red-400 hover:bg-background-tertiary disabled:opacity-50"
                >
                  <X size={15} /> {t("approval.reject")}
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "accent" | "muted" | "danger";
}) {
  const toneClass =
    tone === "accent"
      ? "text-accent"
      : tone === "danger"
        ? "text-red-400"
        : tone === "muted"
          ? "text-foreground-muted"
          : "text-foreground";
  return (
    <div className="rounded-lg border border-border bg-background-secondary p-3">
      <p className="text-xs text-foreground-muted">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${toneClass}`}>{value}</p>
    </div>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors ${
        on ? "bg-accent" : "bg-background-tertiary"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          on ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
  );
}
