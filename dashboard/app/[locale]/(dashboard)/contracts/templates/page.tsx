"use client";

/**
 * Contract-template authoring (/contracts/templates).
 *
 * `contract_templates` had one writer — the seeder — and no screen at all, which
 * made two things impossible: installing the real legal text over the shipped DEV
 * PLACEHOLDER, and recovering a database whose seeders had not run (with the table
 * empty, NO contract can be created and the entire signing chain is dead).
 *
 * The editor's job is not CRUD, it is the placeholder check. `render._fill`
 * substitutes an unknown `{{ name }}` with an EMPTY STRING — no error anywhere —
 * so a mistyped placeholder ships as a legally binding document with a hole in it.
 * The shipped commitment letter had eight of them and named neither party. Hence
 * Check-before-Save, and a preview that fills with visible `[stand_in]` tokens
 * rather than realistic values, because realistic values HIDE a missing one.
 *
 * Reads follow the `contracts` page grant; writes are administrator-only and the
 * API enforces that — this screen only reflects it (403 → an explanatory notice).
 */

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileCode, Plus } from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

interface TemplateSummary {
  id: number;
  code: string;
  kind: string;
  name_ru: string;
  name_uz: string | null;
  name_en: string | null;
  version: number;
  is_active: boolean;
  created_at: string;
  usage_count: number;
}

interface TemplateDetail extends TemplateSummary {
  body: string;
  variables_schema: Record<string, unknown>;
  body_storage_path: string;
  warnings: string[];
}

interface CheckResult {
  ok: boolean;
  unknown: string[];
  used: string[];
  renderable: string[];
  warnings: string[];
}

interface Draft {
  code: string;
  kind: string;
  name_ru: string;
  name_uz: string;
  name_en: string;
  body: string;
  schemaText: string;
  is_active: boolean;
}

const EMPTY_DRAFT: Draft = {
  code: "",
  kind: "contract",
  name_ru: "",
  name_uz: "",
  name_en: "",
  body: "",
  schemaText: '{\n  "type": "object",\n  "required": [],\n  "properties": {}\n}',
  is_active: true,
};

function detailToDraft(d: TemplateDetail): Draft {
  return {
    code: d.code,
    kind: d.kind,
    name_ru: d.name_ru,
    name_uz: d.name_uz ?? "",
    name_en: d.name_en ?? "",
    body: d.body,
    schemaText: JSON.stringify(d.variables_schema ?? {}, null, 2),
    is_active: d.is_active,
  };
}

export default function ContractTemplatesPage() {
  const t = useTranslations("contractTemplates");
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [loadedId, setLoadedId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [check, setCheck] = useState<CheckResult | null>(null);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin-contract-templates"],
    queryFn: () => apiFetch<TemplateSummary[]>("/admin/contract-templates"),
  });

  const detailQuery = useQuery({
    queryKey: ["admin-contract-template", selected],
    queryFn: () => apiFetch<TemplateDetail>(`/admin/contract-templates/${selected}`),
    enabled: selected != null && !creating,
  });

  // Load the fetched row into the editor by ADJUSTING STATE DURING RENDER rather
  // than in an effect. React re-renders immediately without committing the first
  // pass, so the editor never flashes the previous template's body — and an effect
  // here is the cascading-render antipattern `react-hooks/set-state-in-effect`
  // exists to catch. `loadedId` is what makes it fire once per template; it is
  // cleared by `startCreate` so returning to a template already loaded still
  // reloads it over the blank new-template draft.
  if (detailQuery.data && !creating && detailQuery.data.id !== loadedId) {
    setLoadedId(detailQuery.data.id);
    setDraft(detailToDraft(detailQuery.data));
    setCheck(null);
    setPreviewHtml(null);
    setSaveError(null);
  }

  /** `null` while the JSON is unparseable — Check and Save stay disabled. */
  const parsedSchema = useMemo<Record<string, unknown> | null>(() => {
    try {
      const value: unknown = JSON.parse(draft.schemaText);
      return value && typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : null;
    } catch {
      return null;
    }
  }, [draft.schemaText]);

  const checkMutation = useMutation({
    mutationFn: () =>
      apiFetch<CheckResult>("/admin/contract-templates/check", {
        method: "POST",
        body: JSON.stringify({
          body: draft.body,
          kind: draft.kind,
          variables_schema: parsedSchema ?? {},
        }),
      }),
    onSuccess: (result) => setCheck(result),
  });

  const previewMutation = useMutation({
    mutationFn: () =>
      apiFetch<{ html: string; warnings: string[] }>("/admin/contract-templates/preview", {
        method: "POST",
        body: JSON.stringify({
          body: draft.body,
          kind: draft.kind,
          variables_schema: parsedSchema ?? {},
        }),
      }),
    onSuccess: (result) => setPreviewHtml(result.html),
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const schema = parsedSchema ?? {};
      if (creating) {
        return apiFetch<TemplateDetail>("/admin/contract-templates", {
          method: "POST",
          body: JSON.stringify({
            code: draft.code,
            kind: draft.kind,
            name_ru: draft.name_ru,
            name_uz: draft.name_uz || null,
            name_en: draft.name_en || null,
            body: draft.body,
            variables_schema: schema,
            is_active: draft.is_active,
          }),
        });
      }
      return apiFetch<TemplateDetail>(`/admin/contract-templates/${selected}`, {
        method: "PUT",
        body: JSON.stringify({
          name_ru: draft.name_ru,
          name_uz: draft.name_uz || null,
          name_en: draft.name_en || null,
          body: draft.body,
          variables_schema: schema,
          is_active: draft.is_active,
        }),
      });
    },
    onSuccess: async (saved) => {
      setSaveError(null);
      setCreating(false);
      setSelected(saved.id);
      await queryClient.invalidateQueries({ queryKey: ["admin-contract-templates"] });
      await queryClient.invalidateQueries({ queryKey: ["admin-contract-template", saved.id] });
    },
    onError: (error: unknown) => setSaveError(describeError(error, t)),
  });

  function describeError(error: unknown, tr: ReturnType<typeof useTranslations>): string {
    if (error instanceof ApiError) {
      const body = error.body as { detail?: { error?: string; unknown?: string[] } } | null;
      const detail = body?.detail;
      if (detail?.error === "template_body_invalid") {
        return `${tr("errUnknownPlaceholders")}: ${(detail.unknown ?? []).join(", ")}`;
      }
      if (detail?.error === "duplicate_code") return tr("errDuplicateCode");
      if (error.status === 403) return tr("errAdminOnly");
    }
    return tr("errSaveFailed");
  }

  function startCreate(): void {
    setCreating(true);
    setSelected(null);
    setLoadedId(null);
    setDraft(EMPTY_DRAFT);
    setCheck(null);
    setPreviewHtml(null);
    setSaveError(null);
  }

  const canSave =
    parsedSchema !== null &&
    draft.name_ru.trim().length > 0 &&
    draft.body.trim().length > 0 &&
    (!creating || /^[A-Z][A-Z0-9_]{2,63}$/.test(draft.code));

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center gap-2">
        <FileCode className="h-5 w-5 text-foreground-muted" />
        <h1 className="text-xl font-semibold">{t("title")}</h1>
      </div>
      <p className="mb-2 text-sm text-foreground-muted">{t("subtitle")}</p>
      <Link
        href="/contracts"
        className="mb-4 inline-flex items-center gap-1 text-sm text-accent hover:underline"
      >
        <ArrowLeft className="h-4 w-4" />
        {t("backToContracts")}
      </Link>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        {/* ── list ─────────────────────────────────────────────────────── */}
        <div>
          <button
            type="button"
            onClick={startCreate}
            className="mb-3 inline-flex items-center gap-1 rounded border border-border px-3 py-1.5 text-sm hover:bg-background-tertiary"
          >
            <Plus className="h-4 w-4" />
            {t("newTemplate")}
          </button>

          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-background-secondary text-left text-xs text-foreground-muted">
                <tr>
                  <th className="px-3 py-2">{t("colCode")}</th>
                  <th className="px-3 py-2">{t("colKind")}</th>
                  <th className="px-3 py-2">{t("colVersion")}</th>
                  <th className="px-3 py-2">{t("colUsage")}</th>
                </tr>
              </thead>
              <tbody>
                {listQuery.data?.map((tpl) => (
                  <tr
                    key={tpl.id}
                    onClick={() => {
                      setCreating(false);
                      setSelected(tpl.id);
                    }}
                    className={`cursor-pointer border-t border-border hover:bg-background-tertiary ${
                      selected === tpl.id && !creating ? "bg-background-tertiary" : ""
                    }`}
                  >
                    <td className="px-3 py-2">
                      <div className="font-medium">{tpl.code}</div>
                      <div className="text-xs text-foreground-muted">{tpl.name_ru}</div>
                      {!tpl.is_active && (
                        <span className="mt-1 inline-block rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                          {t("inactive")}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs">{t(`kind.${tpl.kind}`)}</td>
                    <td className="px-3 py-2">v{tpl.version}</td>
                    <td className="px-3 py-2">{tpl.usage_count}</td>
                  </tr>
                ))}
                {listQuery.data?.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-3 py-6 text-center text-foreground-muted">
                      {t("empty")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── editor ───────────────────────────────────────────────────── */}
        <div className="rounded-lg border border-border p-4">
          {!creating && selected == null ? (
            <p className="text-sm text-foreground-muted">{t("selectHint")}</p>
          ) : (
            <div className="space-y-3">
              {creating ? (
                <label className="block text-sm">
                  <span className="text-foreground-muted">{t("fieldCode")}</span>
                  <input
                    value={draft.code}
                    onChange={(e) => setDraft({ ...draft, code: e.target.value.toUpperCase() })}
                    placeholder="SUPPLY_V3"
                    className="mt-1 w-full rounded border border-border bg-background px-2 py-1 font-mono text-sm"
                  />
                  <span className="text-xs text-foreground-muted">{t("hintCode")}</span>
                </label>
              ) : (
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-sm font-semibold">{draft.code}</span>
                  <span className="text-xs text-foreground-muted">
                    v{detailQuery.data?.version} · {t(`kind.${draft.kind}`)} ·{" "}
                    {detailQuery.data && formatTashkent(detailQuery.data.created_at)}
                  </span>
                </div>
              )}

              {creating && (
                <label className="block text-sm">
                  <span className="text-foreground-muted">{t("fieldKind")}</span>
                  <select
                    value={draft.kind}
                    onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
                    className="mt-1 w-full rounded border border-border bg-background px-2 py-1 text-sm"
                  >
                    <option value="contract">{t("kind.contract")}</option>
                    <option value="sample_letter">{t("kind.sample_letter")}</option>
                  </select>
                  <span className="text-xs text-foreground-muted">{t("hintKind")}</span>
                </label>
              )}

              <div className="grid gap-2 sm:grid-cols-3">
                {(["name_ru", "name_uz", "name_en"] as const).map((field) => (
                  <label key={field} className="block text-sm">
                    <span className="text-foreground-muted">{t(`field_${field}`)}</span>
                    <input
                      value={draft[field]}
                      onChange={(e) => setDraft({ ...draft, [field]: e.target.value })}
                      className="mt-1 w-full rounded border border-border bg-background px-2 py-1 text-sm"
                    />
                  </label>
                ))}
              </div>

              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.is_active}
                  onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })}
                />
                <span>{t("fieldActive")}</span>
                <span className="text-xs text-foreground-muted">{t("hintActive")}</span>
              </label>

              <label className="block text-sm">
                <span className="text-foreground-muted">{t("fieldBody")}</span>
                <textarea
                  value={draft.body}
                  onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                  rows={14}
                  spellCheck={false}
                  className="mt-1 w-full rounded border border-border bg-background px-2 py-1 font-mono text-xs"
                />
              </label>

              <label className="block text-sm">
                <span className="text-foreground-muted">{t("fieldSchema")}</span>
                <textarea
                  value={draft.schemaText}
                  onChange={(e) => setDraft({ ...draft, schemaText: e.target.value })}
                  rows={8}
                  spellCheck={false}
                  className={`mt-1 w-full rounded border bg-background px-2 py-1 font-mono text-xs ${
                    parsedSchema === null ? "border-red-400" : "border-border"
                  }`}
                />
                {parsedSchema === null && (
                  <span className="text-xs text-red-600">{t("errSchemaJson")}</span>
                )}
              </label>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={parsedSchema === null || checkMutation.isPending}
                  onClick={() => checkMutation.mutate()}
                  className="rounded border border-border px-3 py-1.5 text-sm hover:bg-background-tertiary disabled:opacity-50"
                >
                  {t("check")}
                </button>
                <button
                  type="button"
                  disabled={parsedSchema === null || previewMutation.isPending}
                  onClick={() => previewMutation.mutate()}
                  className="rounded border border-border px-3 py-1.5 text-sm hover:bg-background-tertiary disabled:opacity-50"
                >
                  {t("preview")}
                </button>
                <button
                  type="button"
                  disabled={!canSave || saveMutation.isPending}
                  onClick={() => saveMutation.mutate()}
                  className="rounded bg-accent px-3 py-1.5 text-sm text-white hover:opacity-90 disabled:opacity-50"
                >
                  {creating ? t("create") : t("save")}
                </button>
              </div>

              {saveError && (
                <p className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {saveError}
                </p>
              )}

              {check && (
                <div
                  className={`rounded border px-3 py-2 text-sm ${
                    check.ok
                      ? "border-green-300 bg-green-50 text-green-800"
                      : "border-red-300 bg-red-50 text-red-700"
                  }`}
                >
                  {check.ok ? (
                    <p>{t("checkOk", { count: check.used.length })}</p>
                  ) : (
                    <p>
                      {t("errUnknownPlaceholders")}: <code>{check.unknown.join(", ")}</code>
                    </p>
                  )}
                  {check.warnings.map((w) => (
                    <p key={w} className="mt-1 text-xs text-amber-700">
                      {w}
                    </p>
                  ))}
                  <details className="mt-2 text-xs">
                    <summary className="cursor-pointer text-foreground-muted">
                      {t("renderableNames")}
                    </summary>
                    <code className="break-all">{check.renderable.join(", ")}</code>
                  </details>
                </div>
              )}

              {previewHtml !== null && (
                <div>
                  <p className="mb-1 text-sm text-foreground-muted">{t("previewHint")}</p>
                  <iframe
                    title={t("preview")}
                    srcDoc={previewHtml}
                    sandbox=""
                    className="h-96 w-full rounded border border-border bg-white"
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
