"use client";

/**
 * Reports (/reports) — news-engine review (Phase 3).
 *
 * Analyst/admin review the daily market report: generate now, then approve →
 * publish (publish makes it public on the webapp News tab and posts to the
 * Telegram channel). Backed by /api/v1/admin/reports.
 */

import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Newspaper } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface AdminReport {
  id: number;
  title: string;
  status: "draft" | "pending_approval" | "approved" | "published" | "rejected";
  content_md: string;
  generated_by: string | null;
  period_start: string;
  period_end: string;
  published_at: string | null;
  created_at: string;
}

const STATUS_CLASS: Record<string, string> = {
  draft: "bg-background-tertiary text-foreground-muted",
  pending_approval: "bg-amber-500/20 text-amber-400",
  approved: "bg-blue-500/20 text-blue-400",
  published: "bg-accent/20 text-accent",
  rejected: "bg-red-500/20 text-red-400",
};

export default function ReportsPage() {
  const t = useTranslations("reports");
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery<AdminReport[]>({
    queryKey: ["admin-reports"],
    queryFn: () => apiFetch<AdminReport[]>("/admin/reports"),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-reports"] });

  const generate = useMutation({
    mutationFn: () => apiFetch("/admin/reports/generate", { method: "POST" }),
    onSuccess: invalidate,
  });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "approve" | "publish" | "reject" }) =>
      apiFetch(`/admin/reports/${id}/${action}`, { method: "POST" }),
    onSuccess: invalidate,
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Newspaper size={24} className="text-foreground-muted" aria-hidden="true" />
          <div>
            <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
            <p className="text-sm text-foreground-muted mt-1">{t("subtitle")}</p>
          </div>
        </div>
        <button
          type="button"
          disabled={generate.isPending}
          onClick={() => generate.mutate()}
          className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
        >
          {t("generate")}
        </button>
      </div>

      {isLoading && <p className="text-sm text-foreground-muted">…</p>}
      {isError && <p className="text-sm text-red-400">{t("error")}</p>}
      {data && data.length === 0 && <p className="text-sm text-foreground-muted">{t("empty")}</p>}

      <div className="flex flex-col gap-4">
        {data?.map((r) => (
          <div key={r.id} className="rounded-lg border border-border bg-background-secondary p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-base font-semibold text-foreground">{r.title}</p>
                <p className="text-xs text-foreground-muted mt-1">
                  {r.generated_by ?? "—"} · {r.created_at.slice(0, 10)}
                </p>
              </div>
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_CLASS[r.status] ?? STATUS_CLASS.draft}`}
              >
                {t(`status.${r.status}`)}
              </span>
            </div>

            <pre className="mt-3 whitespace-pre-wrap rounded-md border border-border bg-background p-3 text-sm text-foreground font-sans">
              {r.content_md.replace(/[*_]/g, "")}
            </pre>

            <div className="mt-3 flex gap-2">
              {r.status !== "published" && (
                <>
                  {r.status !== "approved" && (
                    <button
                      type="button"
                      disabled={act.isPending}
                      onClick={() => act.mutate({ id: r.id, action: "approve" })}
                      className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary disabled:opacity-50"
                    >
                      {t("approve")}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={act.isPending}
                    onClick={() => act.mutate({ id: r.id, action: "publish" })}
                    className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
                  >
                    {t("publish")}
                  </button>
                  <button
                    type="button"
                    disabled={act.isPending}
                    onClick={() => act.mutate({ id: r.id, action: "reject" })}
                    className="rounded-md border border-border px-4 py-2 text-sm font-medium text-red-400 hover:bg-background-tertiary disabled:opacity-50"
                  >
                    {t("reject")}
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
