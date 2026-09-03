"use client";

/**
 * News Admin (/admin/news) — news OPERATIONS.
 *
 * Live state and one-off actions, not configuration:
 *  - News-ops stats (GET /admin/news/stats) + Run-Parser / Generate-Report actions.
 *  - Per-source scan activity (GET /admin/news/activity), polled.
 *  - Source groups (GET /admin/source-groups, PUT /admin/sources/{id}/group).
 *  - Approval queue (GET /admin/news/pending, POST /{id}/approve|reject).
 *
 * The runtime switches used to be here too, and for a while that was the only
 * place to see them. They now live at `/admin/settings/news`, which shows the
 * env default beside the running value and lets an operator change one. Keeping
 * a copy here meant this page rendered ALL THIRTY settings — the Didox partner
 * token and the escrow rail included, twenty-three of them nothing to do with
 * news — under a hint telling the reader to go and edit `.env`, which migration
 * 0045 made untrue. Two screens disagreeing about the same values is worse than
 * one screen fewer.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, Play, RefreshCw, SlidersHorizontal, X } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

interface SourceBrief {
  id: number;
  name: string;
  adapter: string;
  country: string | null;
  group_name: string | null;
  is_enabled: boolean;
}

interface SourceGroup {
  group: string | null;
  total: number;
  active: number;
}

interface SourceActivity {
  id: number;
  name: string;
  adapter: string;
  group_name: string | null;
  is_enabled: boolean;
  last_fetch_at: string | null;
  last_success_at: string | null;
  consecutive_failures: number;
  raw_24h: number;
  news_24h: number;
}

interface RunParserResult {
  enqueued: string[];
  sources: string[];
  count: number;
}

interface SourceDetail {
  id: number;
  name: string;
  adapter: string;
  kind: string;
  country: string | null;
  group_name: string | null;
  url: string | null;
  is_enabled: boolean;
  last_test_ok_at: string | null;
  config: Record<string, unknown>;
}

interface SourceTestOut {
  ok: boolean;
  sample_rows: unknown[];
  error: string | null;
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
  ai_status: "on" | "off" | "error";
  ai_errors_recent: number;
  ai_last_error: string | null;
  budget_used_pct: number;
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
  const { isAdmin } = useAuth();

  // ── Queries ──────────────────────────────────────────────────────────────
  const stats = useQuery<NewsStats>({
    queryKey: ["news-stats"],
    queryFn: () => apiFetch<NewsStats>("/admin/news/stats"),
  });
  const pending = useQuery<PendingNewsItem[]>({
    queryKey: ["news-pending"],
    queryFn: () => apiFetch<PendingNewsItem[]>("/admin/news/pending"),
  });
  const activity = useQuery<SourceActivity[]>({
    queryKey: ["news-activity"],
    queryFn: () => apiFetch<SourceActivity[]>("/admin/news/activity"),
    refetchInterval: 10_000, // keep the "what's happening" view live as workers complete
  });
  const groups = useQuery<SourceGroup[]>({
    queryKey: ["source-groups"],
    queryFn: () => apiFetch<SourceGroup[]>("/admin/source-groups"),
    enabled: isAdmin,
  });
  const sources = useQuery<SourceBrief[]>({
    queryKey: ["sources-brief"],
    queryFn: () => apiFetch<SourceBrief[]>("/admin/sources/brief"),
    enabled: isAdmin,
  });

  // ── Local edit buffers ──────────────────────────────────────────────────
  const [groupEdits, setGroupEdits] = useState<Record<number, string>>({});
  const [editId, setEditId] = useState<number | null>(null);

  // ── Mutations ────────────────────────────────────────────────────────────
  const invalidate = (keys: string[]) =>
    keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));

  const [runMsg, setRunMsg] = useState<string | null>(null);
  const runParser = useMutation({
    mutationFn: () => apiFetch<RunParserResult>("/admin/news/run-parser", { method: "POST" }),
    onSuccess: (res) => {
      setRunMsg(
        res.count > 0
          ? `${t("activity.scanning")} (${res.count}): ${res.sources.join(", ")}`
          : t("activity.noSources"),
      );
      invalidate(["news-stats", "news-activity"]);
    },
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
  const setGroup = useMutation({
    mutationFn: ({ id, group }: { id: number; group: string }) =>
      apiFetch(`/admin/sources/${id}/group`, { method: "PUT", body: JSON.stringify({ group }) }),
    onSuccess: (_data, vars) => {
      setGroupEdits((e) => {
        const next = { ...e };
        delete next[vars.id];
        return next;
      });
      invalidate(["source-groups", "sources-brief"]);
    },
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
          label={t("stats.budget")}
          value={s ? `${s.budget_used_pct}%` : "…"}
          tone={s ? (s.budget_used_pct >= 90 ? "danger" : "default") : "default"}
        />
        <StatCard
          label={t("stats.aiStatus")}
          value={s ? t(`stats.${s.ai_status}`) : "…"}
          tone={s ? (s.ai_status === "error" ? "danger" : s.ai_status === "on" ? "accent" : "muted") : "default"}
        />
      </div>

      {/* AI failing — surface the error instead of silent zeros */}
      {s?.ai_status === "error" && (
        <div className="rounded-md border border-red-400/40 bg-red-500/10 px-4 py-3">
          <p className="text-sm font-semibold text-red-400">
            {t("aiError.title")}
            {s.ai_errors_recent > 0 ? ` · ${s.ai_errors_recent}` : ""}
          </p>
          <p className="mt-1 text-sm text-foreground-muted">{t("aiError.hint")}</p>
          {s.ai_last_error && (
            <p className="mt-2 break-all rounded bg-background p-2 font-mono text-xs text-foreground">
              {s.ai_last_error}
            </p>
          )}
        </div>
      )}

      {/* Run-parser feedback: which sources the scan hit */}
      {runMsg && (
        <div className="rounded-md border border-accent/40 bg-accent/10 px-4 py-2 text-sm text-foreground">
          {runMsg}
        </div>
      )}

      {/* ── Scan activity ──────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-background-secondary p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold text-foreground">{t("activity.title")}</h2>
          <button
            type="button"
            onClick={() => activity.refetch()}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-background-tertiary"
          >
            <RefreshCw size={13} className={activity.isFetching ? "animate-spin" : ""} />
            {t("activity.refresh")}
          </button>
        </div>
        {activity.data && activity.data.length === 0 && (
          <p className="text-sm text-foreground-muted">{t("activity.empty")}</p>
        )}
        {activity.data && activity.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-foreground-muted">
                  <th className="pb-2 pe-3 font-medium">{t("activity.source")}</th>
                  <th className="pb-2 pe-3 font-medium">{t("activity.lastScan")}</th>
                  <th className="pb-2 pe-3 font-medium">{t("activity.lastSuccess")}</th>
                  <th className="pb-2 pe-3 text-right font-medium">{t("activity.fails")}</th>
                  <th className="pb-2 pe-3 text-right font-medium">{t("activity.raw")}</th>
                  <th className="pb-2 text-right font-medium">{t("activity.news")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {activity.data.map((a) => {
                  const dot = !a.is_enabled
                    ? "bg-foreground-muted"
                    : a.consecutive_failures > 0
                      ? "bg-red-400"
                      : a.last_success_at
                        ? "bg-accent"
                        : "bg-amber-400";
                  return (
                    <tr key={a.id} className="text-foreground">
                      <td className="py-2 pe-3">
                        <span className="flex items-center gap-2">
                          <span className={`h-2 w-2 flex-shrink-0 rounded-full ${dot}`} aria-hidden="true" />
                          <span className="min-w-0">
                            <span className="block truncate">{a.name}</span>
                            <span className="block text-xs text-foreground-muted">
                              {a.adapter}
                              {a.group_name ? ` · ${a.group_name}` : ""}
                              {!a.is_enabled ? ` · ${t("groups.disabled")}` : ""}
                            </span>
                          </span>
                        </span>
                      </td>
                      <td className="py-2 pe-3 text-foreground-muted">
                        {fmtDateTime(a.last_fetch_at, t("stats.never"))}
                      </td>
                      <td className="py-2 pe-3 text-foreground-muted">
                        {fmtDateTime(a.last_success_at, t("stats.never"))}
                      </td>
                      <td className={`py-2 pe-3 text-right ${a.consecutive_failures > 0 ? "text-red-400" : "text-foreground-muted"}`}>
                        {a.consecutive_failures}
                      </td>
                      <td className="py-2 pe-3 text-right text-foreground-muted">{a.raw_24h}</td>
                      <td className="py-2 text-right font-medium text-foreground">{a.news_24h}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-foreground-muted">{t("activity.hint")}</p>
          </div>
        )}
      </section>

      {/* ── Source groups (admin only) ─────────────────────────────────────── */}
      {isAdmin && (
        <section className="rounded-lg border border-border bg-background-secondary p-4">
          <h2 className="mb-3 text-base font-semibold text-foreground">{t("groups.title")}</h2>
          {/* Group summary chips */}
          <div className="mb-4 flex flex-wrap gap-2">
            {groups.data?.map((g) => (
              <span
                key={g.group ?? "__none"}
                className="inline-flex items-center gap-2 rounded-full border border-border bg-background px-3 py-1 text-xs text-foreground"
              >
                <span className="font-medium">{g.group ?? t("groups.ungrouped")}</span>
                <span className="text-foreground-muted">
                  {g.active}/{g.total}
                </span>
              </span>
            ))}
          </div>
          {/* Per-source group assignment */}
          <ul className="flex flex-col divide-y divide-border">
            {sources.data?.map((src) => {
              const current = src.group_name ?? "";
              const draft = src.id in groupEdits ? groupEdits[src.id]! : current;
              const changed = draft !== current;
              return (
                <li key={src.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-sm text-foreground">
                      {src.name}
                      {!src.is_enabled && (
                        <span className="ms-2 text-xs text-foreground-muted">({t("groups.disabled")})</span>
                      )}
                    </p>
                    <p className="text-xs text-foreground-muted">{src.adapter}</p>
                  </div>
                  <div className="flex flex-shrink-0 items-center gap-2">
                    <input
                      value={draft}
                      placeholder={t("groups.ungrouped")}
                      onChange={(e) =>
                        setGroupEdits((prev) => ({ ...prev, [src.id]: e.target.value }))
                      }
                      className="w-40 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
                    />
                    <button
                      type="button"
                      disabled={!changed || setGroup.isPending}
                      onClick={() => setGroup.mutate({ id: src.id, group: draft })}
                      className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-30"
                    >
                      {t("actions.save")}
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditId(src.id)}
                      className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-background-tertiary"
                    >
                      <Pencil size={14} /> {t("edit.button")}
                    </button>
                  </div>
                </li>
              );
            })}
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

      {editId != null && (
        <EditSourceDialog
          sourceId={editId}
          onClose={() => setEditId(null)}
          onSaved={() => invalidate(["sources-brief", "source-groups", "news-activity"])}
        />
      )}
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

interface EditForm {
  name: string;
  url: string;
  contentKind: string;
  country: string;
  group: string;
  enabled: boolean;
}

function EditSourceDialog({
  sourceId,
  onClose,
  onSaved,
}: {
  sourceId: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("newsAdmin");
  const detail = useQuery<SourceDetail>({
    queryKey: ["source", sourceId],
    queryFn: () => apiFetch<SourceDetail>(`/sources/${sourceId}`),
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-border bg-background-secondary p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">
            {t("edit.title")}
            {detail.data ? ` · ${detail.data.adapter}` : ""}
          </h3>
          <button type="button" onClick={onClose} className="text-foreground-muted hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        {detail.isLoading || !detail.data ? (
          <p className="text-sm text-foreground-muted">…</p>
        ) : (
          <EditSourceForm source={detail.data} onClose={onClose} onSaved={onSaved} />
        )}
      </div>
    </div>
  );
}

function EditSourceForm({
  source,
  onClose,
  onSaved,
}: {
  source: SourceDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("newsAdmin");
  const [form, setForm] = useState<EditForm>(() => {
    const cfg = source.config ?? {};
    return {
      name: source.name ?? "",
      url: String(cfg.url ?? cfg.feed_url ?? source.url ?? ""),
      contentKind: String(cfg.content_kind ?? ""),
      country: source.country ?? "",
      group: source.group_name ?? "",
      enabled: source.is_enabled,
    };
  });
  const [testResult, setTestResult] = useState<SourceTestOut | null>(null);

  const origUrl = String(source.config?.url ?? source.config?.feed_url ?? source.url ?? "");
  const origKind = String(source.config?.content_kind ?? "");
  const configChanged = form.url !== origUrl || form.contentKind !== origKind;

  const test = useMutation({
    mutationFn: () => apiFetch<SourceTestOut>(`/sources/${source.id}/test`, { method: "POST" }),
    onSuccess: (r) => setTestResult(r),
  });
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        name: form.name,
        country: form.country,
        group_name: form.group,
      };
      if (configChanged) {
        // Editing the feed re-validates + disables server-side until re-tested.
        const cfg: Record<string, unknown> = { ...(source.config ?? {}) };
        cfg.url = form.url;
        if (form.contentKind) cfg.content_kind = form.contentKind;
        else delete cfg.content_kind;
        body.config = cfg;
      } else {
        body.is_enabled = form.enabled; // enable-toggle only applies when feed unchanged
      }
      return apiFetch(`/sources/${source.id}`, { method: "PATCH", body: JSON.stringify(body) });
    },
    onSuccess: () => {
      onSaved();
      onClose();
    },
  });

  return (
    <div className="flex flex-col gap-3">
      <Field label={t("edit.name")}>
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
        />
      </Field>
      <Field label={t("edit.feedUrl")}>
        <input
          value={form.url}
          onChange={(e) => setForm({ ...form, url: e.target.value })}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t("edit.contentKind")}>
          <select
            value={form.contentKind}
            onChange={(e) => setForm({ ...form, contentKind: e.target.value })}
            className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <option value="news">news</option>
            <option value="">—</option>
          </select>
        </Field>
        <Field label={t("edit.country")}>
          <input
            value={form.country}
            placeholder={t("edit.countryPh")}
            onChange={(e) => setForm({ ...form, country: e.target.value })}
            className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
          />
        </Field>
      </div>
      <Field label={t("groups.title")}>
        <input
          value={form.group}
          placeholder={t("groups.ungrouped")}
          onChange={(e) => setForm({ ...form, group: e.target.value })}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
        />
      </Field>

      {!configChanged && (
        <label className="flex items-center gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            disabled={!source.last_test_ok_at}
          />
          {t("edit.enabled")}
          {!source.last_test_ok_at && (
            <span className="text-xs text-foreground-muted">({t("edit.needsTest")})</span>
          )}
        </label>
      )}

      {configChanged && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
          {t("edit.feedChangedNote")}
        </p>
      )}

      {testResult && (
        <p
          className={`rounded-md px-3 py-2 text-xs ${
            testResult.ok ? "bg-accent/10 text-accent" : "bg-red-500/10 text-red-400"
          }`}
        >
          {testResult.ok
            ? `${t("edit.testOk")} (${testResult.sample_rows.length})`
            : `${t("edit.testFail")}: ${testResult.error ?? ""}`}
        </p>
      )}

      <div className="mt-2 flex justify-end gap-2">
        <button
          type="button"
          disabled={test.isPending}
          onClick={() => test.mutate()}
          className="rounded-md border border-border px-4 py-1.5 text-sm font-medium text-foreground hover:bg-background-tertiary disabled:opacity-50"
        >
          {test.isPending ? "…" : t("edit.test")}
        </button>
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => save.mutate()}
          className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
        >
          {save.isPending ? "…" : t("actions.save")}
        </button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-foreground-muted">{label}</span>
      {children}
    </label>
  );
}

