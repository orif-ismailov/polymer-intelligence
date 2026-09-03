"use client";

/**
 * The news prompt editor (on /admin/settings/news).
 *
 * The instruction the AI reads before classifying every article. Until this
 * existed, changing it needed a developer, a commit and a deploy — the same gap
 * the settings panel around it closed for every switch.
 *
 * SAVING CREATES A NEW VERSION; it never rewrites one. That is not caution for
 * its own sake: the backend caches the loaded prompt per process keyed on the
 * version string, so a mutable body would leave some workers running the old
 * text and some the new, with every `parse_runs` row from both claiming the same
 * version. Afterwards nothing could say which article got which prompt, and that
 * is not repairable. See `backend/app/models/prompts.py`.
 *
 * Saving and activating are therefore two acts, and the Try button sits between
 * them. That ordering is the whole screen: write it, see what it does to a real
 * article, then turn it on.
 *
 * No hardcoded hex.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

interface PromptVersionItem {
  version: string;
  shipped: boolean;
  active: boolean;
  created_by: string | null;
  created_at: string | null;
  note: string | null;
  size: number;
}

interface NewsPrompt {
  active_version: string;
  body: string;
  shipped: boolean;
  next_version: string;
  max_chars: number;
  versions: PromptVersionItem[];
}

interface TryResult {
  raw_item_id: number;
  excerpt: string;
  article: Record<string, unknown>;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
}

/** The handful of classification fields worth reading at a glance. */
const TRY_FIELDS = [
  "is_relevant",
  "category",
  "importance",
  "market_impact",
  "confidence",
  "related_products",
  "companies",
  "country",
] as const;

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "boolean") return String(value);
  return String(value);
}

export function NewsPromptEditor({ canWrite }: { canWrite: boolean }) {
  const t = useTranslations("adminSettings.prompt");
  const qc = useQueryClient();

  // Same idiom as the setting rows above: `null` means "not editing", so a
  // background refetch cannot overwrite what the operator is typing.
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [trial, setTrial] = useState<TryResult | null>(null);

  const prompt = useQuery<NewsPrompt>({
    queryKey: ["news-prompt"],
    queryFn: () => apiFetch<NewsPrompt>("/admin/settings/news-prompt"),
  });

  const body = draft ?? prompt.data?.body ?? "";
  const dirty = draft !== null && draft !== prompt.data?.body;

  const describeError = (e: unknown, fallback: string): string => {
    if (e instanceof ApiError) {
      const detail = (e.body as { detail?: unknown })?.detail;
      if (typeof detail === "string") return detail;
    }
    return fallback;
  };

  const save = useMutation({
    mutationFn: () =>
      apiFetch<NewsPrompt>("/admin/settings/news-prompt", {
        method: "POST",
        body: JSON.stringify({ body }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["news-prompt"] });
      // The version list changed, so the version dropdown in the settings rows
      // above has to be refetched too — it is the control that activates one.
      void qc.invalidateQueries({ queryKey: ["admin-settings"] });
      setDraft(null);
      setError(null);
    },
    onError: (e) => setError(describeError(e, t("saveError"))),
  });

  const activate = useMutation({
    mutationFn: (version: string) =>
      apiFetch(`/admin/settings/news_prompt_version`, {
        method: "PUT",
        body: JSON.stringify({ value: version }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["news-prompt"] });
      void qc.invalidateQueries({ queryKey: ["admin-settings"] });
      setError(null);
    },
    onError: (e) => setError(describeError(e, t("activateError"))),
  });

  const tryIt = useMutation({
    mutationFn: () =>
      apiFetch<TryResult>("/admin/settings/news-prompt/try", {
        method: "POST",
        body: JSON.stringify({ body }),
      }),
    onSuccess: (result) => {
      setTrial(result);
      setError(null);
    },
    onError: (e) => setError(describeError(e, t("tryError"))),
  });

  const busy = save.isPending || activate.isPending || tryIt.isPending;
  const tooLong = prompt.data ? body.length > prompt.data.max_chars : false;

  return (
    <section className="rounded-lg border border-border bg-background-secondary p-4">
      <h2 className="text-base font-semibold text-foreground">{t("title")}</h2>
      <p className="mt-1 max-w-prose text-xs leading-relaxed text-foreground-muted">
        {t("subtitle")}
      </p>

      {prompt.isLoading && (
        <p className="mt-3 text-sm text-foreground-muted">{t("loading")}</p>
      )}
      {prompt.isError && <p className="mt-3 text-sm text-red-400">{t("error")}</p>}

      {error && (
        <p
          role="alert"
          className="mt-3 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400"
        >
          {error}
        </p>
      )}

      {prompt.data && (
        <>
          <p className="mt-3 text-xs text-foreground-muted">
            {t("active", { version: prompt.data.active_version })}
            {prompt.data.shipped ? ` · ${t("shipped")}` : ""}
          </p>

          <textarea
            value={body}
            onChange={(e) => setDraft(e.target.value)}
            disabled={!canWrite || busy}
            rows={18}
            spellCheck={false}
            aria-label={t("title")}
            className="mt-2 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs leading-relaxed text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent disabled:opacity-60"
          />

          <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
            <p className={tooLong ? "text-xs text-red-400" : "text-xs text-foreground-muted"}>
              {t("length", { chars: body.length, max: prompt.data.max_chars })}
            </p>
            {canWrite && (
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy || tooLong || !body.trim()}
                  onClick={() => tryIt.mutate()}
                >
                  {tryIt.isPending ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                  ) : (
                    <FlaskConical className="size-4" aria-hidden />
                  )}
                  {t("try")}
                </Button>
                <Button
                  size="sm"
                  disabled={!dirty || busy || tooLong || !body.trim()}
                  onClick={() => save.mutate()}
                >
                  {t("saveAs", { version: prompt.data.next_version })}
                </Button>
              </div>
            )}
          </div>

          {!canWrite && (
            <p className="mt-2 text-xs text-foreground-muted">{t("readOnly")}</p>
          )}

          {trial && (
            <div className="mt-4 rounded-md border border-border bg-background p-3">
              <p className="text-xs font-medium text-foreground">{t("tryResult")}</p>
              <p className="mt-1 text-xs italic leading-relaxed text-foreground-muted">
                {trial.excerpt}
                {trial.excerpt.length >= 600 ? "…" : ""}
              </p>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
                {TRY_FIELDS.map((field) => (
                  <div key={field} className="min-w-0">
                    <dt className="truncate text-xs text-foreground-muted">{field}</dt>
                    <dd className="truncate text-sm text-foreground">
                      {renderValue(trial.article[field])}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-xs text-foreground-muted">
                {t("tryCost", {
                  tokensIn: trial.tokens_in,
                  tokensOut: trial.tokens_out,
                  seconds: (trial.latency_ms / 1000).toFixed(1),
                })}
              </p>
            </div>
          )}

          <h3 className="mt-5 text-sm font-medium text-foreground">{t("versions")}</h3>
          <ul className="mt-1 flex flex-col divide-y divide-border">
            {prompt.data.versions.map((v) => (
              <li key={v.version} className="flex items-center justify-between gap-4 py-2">
                <div className="min-w-0">
                  <p className="text-sm text-foreground">
                    {v.version}
                    {v.active && <span className="ml-2 text-xs text-accent">{t("isActive")}</span>}
                  </p>
                  <p className="truncate text-xs text-foreground-muted">
                    {v.shipped
                      ? t("shipped")
                      : [
                          v.created_by,
                          v.created_at ? formatTashkent(v.created_at) : null,
                          v.note,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                    {` · ${t("chars", { chars: v.size })}`}
                  </p>
                </div>
                {canWrite && !v.active && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => activate.mutate(v.version)}
                  >
                    {t("activate")}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
