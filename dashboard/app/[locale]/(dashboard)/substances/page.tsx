"use client";

/**
 * Substance registry (/substances) — R5 / P5 (FR-C1).
 *
 * This table is the source of truth for regulated chemistry: no machine-readable
 * state registry exists in Uzbekistan, so the ПКМ lists are digitized here by a
 * versioned seed and corrected in this screen. Editing it decides what companies
 * may sell, which is why writes are admin-only while analysts can read (they are
 * the ones answering "why is this offer blocked?").
 *
 * A row is deactivated, never deleted: offers point at substances, and a blocked
 * offer has to stay explainable after the list that blocked it is superseded.
 *
 * Backed by /admin/substances (GET analyst+, POST/PATCH/deactivate admin).
 */

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Pencil, Plus, PowerOff, RotateCcw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

// ─── Types ───────────────────────────────────────────────────────────────────

type Level = "free" | "docs_required" | "license_required" | "prohibited";
type Regime =
  | "precursor_list_iv"
  | "explosive_toxic"
  | "strong_acting"
  | "pkm916_import";

interface Substance {
  id: number;
  code: string;
  name_ru: string;
  name_uz: string | null;
  name_en: string | null;
  hs_code: string;
  cas: string | null;
  hazard_class: string | null;
  regulation_level: Level;
  regulation_regime: Regime | null;
  threshold_concentration_pct: string | null;
  exemption_annual_limit: string | null;
  exemption_unit: string | null;
  license_category: string | null;
  required_docs: string[];
  synonyms: string[];
  source_act: string | null;
  seed_revision: string | null;
  is_active: boolean;
}

const LEVELS: Level[] = ["free", "docs_required", "license_required", "prohibited"];
const REGIMES: Regime[] = [
  "precursor_list_iv",
  "explosive_toxic",
  "strong_acting",
  "pkm916_import",
];
const DOC_KINDS = ["sds", "tds", "coa", "certificate"];

const LEVEL_CLASSES: Record<Level, string> = {
  free: "border-border text-foreground-muted",
  docs_required: "border-sky-500/40 text-sky-400",
  license_required: "border-amber-500/40 text-amber-400",
  prohibited: "border-red-500/40 text-red-400",
};

// ─── Form state ──────────────────────────────────────────────────────────────

interface FormState {
  code: string;
  name_ru: string;
  name_uz: string;
  name_en: string;
  hs_code: string;
  cas: string;
  hazard_class: string;
  regulation_level: Level;
  regulation_regime: Regime | "";
  threshold_concentration_pct: string;
  exemption_annual_limit: string;
  exemption_unit: string;
  license_category: string;
  required_docs: string[];
  synonyms: string;
  source_act: string;
}

const EMPTY_FORM: FormState = {
  code: "",
  name_ru: "",
  name_uz: "",
  name_en: "",
  hs_code: "",
  cas: "",
  hazard_class: "",
  regulation_level: "free",
  regulation_regime: "",
  threshold_concentration_pct: "",
  exemption_annual_limit: "",
  exemption_unit: "",
  license_category: "",
  required_docs: [],
  synonyms: "",
  source_act: "",
};

function toForm(row: Substance): FormState {
  return {
    code: row.code,
    name_ru: row.name_ru,
    name_uz: row.name_uz ?? "",
    name_en: row.name_en ?? "",
    hs_code: row.hs_code,
    cas: row.cas ?? "",
    hazard_class: row.hazard_class ?? "",
    regulation_level: row.regulation_level,
    regulation_regime: row.regulation_regime ?? "",
    threshold_concentration_pct: row.threshold_concentration_pct ?? "",
    exemption_annual_limit: row.exemption_annual_limit ?? "",
    exemption_unit: row.exemption_unit ?? "",
    license_category: row.license_category ?? "",
    required_docs: row.required_docs,
    synonyms: row.synonyms.join(", "),
    source_act: row.source_act ?? "",
  };
}

function toPayload(form: FormState): Record<string, unknown> {
  const orNull = (v: string) => (v.trim() === "" ? null : v.trim());
  return {
    code: form.code.trim(),
    name_ru: form.name_ru.trim(),
    name_uz: orNull(form.name_uz),
    name_en: orNull(form.name_en),
    hs_code: form.hs_code.trim(),
    cas: orNull(form.cas),
    hazard_class: orNull(form.hazard_class),
    regulation_level: form.regulation_level,
    regulation_regime: form.regulation_regime === "" ? null : form.regulation_regime,
    threshold_concentration_pct: orNull(form.threshold_concentration_pct),
    exemption_annual_limit: orNull(form.exemption_annual_limit),
    exemption_unit: orNull(form.exemption_unit),
    license_category: orNull(form.license_category),
    required_docs: form.required_docs,
    synonyms: form.synonyms
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    source_act: orNull(form.source_act),
    is_active: true,
  };
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function SubstancesPage() {
  const t = useTranslations("substances");
  const qc = useQueryClient();
  const { isAdmin } = useAuth();

  const [q, setQ] = useState("");
  const [level, setLevel] = useState<Level | "">("");
  const [editing, setEditing] = useState<Substance | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery<Substance[]>({
    queryKey: ["substances"],
    queryFn: () => apiFetch<Substance[]>("/admin/substances"),
  });

  const save = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      editing
        ? apiFetch(`/admin/substances/${editing.id}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
          })
        : apiFetch("/admin/substances", { method: "POST", body: JSON.stringify(payload) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["substances"] });
      setForm(null);
      setEditing(null);
      setFormError(null);
    },
    onError: (err: unknown) => setFormError(reasonOf(err, t)),
  });

  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      apiFetch(`/admin/substances/${id}/${active ? "activate" : "deactivate"}`, {
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["substances"] }),
  });

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (data ?? []).filter((row) => {
      if (level && row.regulation_level !== level) return false;
      if (!term) return true;
      return [row.code, row.name_ru, row.name_en, row.cas, row.hs_code, ...row.synonyms]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(term));
    });
  }, [data, q, level]);

  function startCreate(): void {
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setFormError(null);
  }

  function startEdit(row: Substance): void {
    setEditing(row);
    setForm(toForm(row));
    setFormError(null);
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <FlaskConical size={24} className="text-foreground-muted" aria-hidden="true" />
          <div>
            <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
            <p className="mt-1 text-sm text-foreground-muted">{t("subtitle")}</p>
          </div>
        </div>
        {isAdmin && (
          <button
            type="button"
            onClick={startCreate}
            className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark"
          >
            <Plus size={16} aria-hidden="true" /> {t("add")}
          </button>
        )}
      </div>

      {/* The registry ships provisional: the ПКМ appendices are not machine-readable
          and a lawyer has to confirm the current wording before the gate goes on. */}
      <p className="rounded-lg border border-amber-500/50 bg-background-secondary p-3 text-sm text-amber-400">
        {t("provisional")}
      </p>

      <div className="flex flex-wrap gap-3">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("searchPlaceholder")}
          className="w-64 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent"
        />
        <select
          value={level}
          onChange={(e) => setLevel(e.target.value as Level | "")}
          className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
        >
          <option value="">{t("allLevels")}</option>
          {LEVELS.map((value) => (
            <option key={value} value={value}>
              {t(`level.${value}`)}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-sm text-foreground-muted">…</p>}
      {isError && <p className="text-sm text-red-400">{t("error")}</p>}
      {data && rows.length === 0 && <p className="text-sm text-foreground-muted">{t("empty")}</p>}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-secondary text-left text-xs uppercase tracking-wider text-foreground-muted">
              <tr>
                <th className="px-4 py-3">{t("columns.name")}</th>
                <th className="px-4 py-3">{t("columns.hs")}</th>
                <th className="px-4 py-3">{t("columns.cas")}</th>
                <th className="px-4 py-3">{t("columns.level")}</th>
                <th className="px-4 py-3">{t("columns.threshold")}</th>
                <th className="px-4 py-3">{t("columns.source")}</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((row) => (
                <tr key={row.id} className={row.is_active ? "" : "opacity-50"}>
                  <td className="px-4 py-3">
                    <p className="font-medium text-foreground">{row.name_ru}</p>
                    <p className="text-xs text-foreground-muted">{row.code}</p>
                  </td>
                  <td className="px-4 py-3 tabular-nums text-foreground">{row.hs_code}</td>
                  <td className="px-4 py-3 tabular-nums text-foreground-muted">{row.cas || "—"}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full border px-2 py-0.5 text-xs ${LEVEL_CLASSES[row.regulation_level]}`}
                    >
                      {t(`level.${row.regulation_level}`)}
                    </span>
                    {row.regulation_regime && (
                      <p className="mt-1 text-xs text-foreground-muted">
                        {t(`regime.${row.regulation_regime}`)}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3 tabular-nums text-foreground-muted">
                    {row.threshold_concentration_pct ? `≥ ${row.threshold_concentration_pct}%` : "—"}
                  </td>
                  <td className="max-w-xs px-4 py-3 text-xs text-foreground-muted">
                    {row.source_act || "—"}
                    {row.seed_revision && (
                      <span className="ms-1 opacity-70">({row.seed_revision})</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {isAdmin && (
                      <>
                        <button
                          type="button"
                          onClick={() => startEdit(row)}
                          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-foreground hover:bg-background-tertiary"
                        >
                          <Pencil size={14} aria-hidden="true" /> {t("edit")}
                        </button>
                        <button
                          type="button"
                          disabled={toggle.isPending}
                          onClick={() => toggle.mutate({ id: row.id, active: !row.is_active })}
                          className="ms-2 inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-foreground-muted hover:bg-background-tertiary disabled:opacity-50"
                        >
                          {row.is_active ? (
                            <>
                              <PowerOff size={14} aria-hidden="true" /> {t("deactivate")}
                            </>
                          ) : (
                            <>
                              <RotateCcw size={14} aria-hidden="true" /> {t("activate")}
                            </>
                          )}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {form && (
        <section className="rounded-lg border border-border bg-background-secondary p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground-muted">
            {editing ? t("editTitle") : t("addTitle")}
          </h2>

          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Field label={t("fields.code")} required>
              <TextInput
                value={form.code}
                disabled={editing !== null}
                onChange={(v) => setForm({ ...form, code: v })}
              />
            </Field>
            <Field label={t("fields.nameRu")} required>
              <TextInput value={form.name_ru} onChange={(v) => setForm({ ...form, name_ru: v })} />
            </Field>
            <Field label={t("fields.nameUz")}>
              <TextInput value={form.name_uz} onChange={(v) => setForm({ ...form, name_uz: v })} />
            </Field>
            <Field label={t("fields.nameEn")}>
              <TextInput value={form.name_en} onChange={(v) => setForm({ ...form, name_en: v })} />
            </Field>
            <Field label={t("fields.hs")} required hint={t("fields.hsHint")}>
              <TextInput value={form.hs_code} onChange={(v) => setForm({ ...form, hs_code: v })} />
            </Field>
            <Field label={t("fields.cas")} hint={t("fields.casHint")}>
              <TextInput value={form.cas} onChange={(v) => setForm({ ...form, cas: v })} />
            </Field>
            <Field label={t("fields.level")} required>
              <select
                value={form.regulation_level}
                onChange={(e) =>
                  setForm({ ...form, regulation_level: e.target.value as Level })
                }
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
              >
                {LEVELS.map((value) => (
                  <option key={value} value={value}>
                    {t(`level.${value}`)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("fields.regime")} hint={t("fields.regimeHint")}>
              <select
                value={form.regulation_regime}
                onChange={(e) =>
                  setForm({ ...form, regulation_regime: e.target.value as Regime | "" })
                }
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
              >
                <option value="">—</option>
                {REGIMES.map((value) => (
                  <option key={value} value={value}>
                    {t(`regime.${value}`)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("fields.threshold")} hint={t("fields.thresholdHint")}>
              <TextInput
                value={form.threshold_concentration_pct}
                onChange={(v) => setForm({ ...form, threshold_concentration_pct: v })}
              />
            </Field>
            <Field label={t("fields.exemption")}>
              <TextInput
                value={form.exemption_annual_limit}
                onChange={(v) => setForm({ ...form, exemption_annual_limit: v })}
              />
            </Field>
            <Field label={t("fields.exemptionUnit")}>
              <TextInput
                value={form.exemption_unit}
                onChange={(v) => setForm({ ...form, exemption_unit: v })}
              />
            </Field>
            <Field label={t("fields.licenseCategory")}>
              <TextInput
                value={form.license_category}
                onChange={(v) => setForm({ ...form, license_category: v })}
              />
            </Field>
            <Field label={t("fields.synonyms")} hint={t("fields.synonymsHint")}>
              <TextInput
                value={form.synonyms}
                onChange={(v) => setForm({ ...form, synonyms: v })}
              />
            </Field>
            <Field label={t("fields.sourceAct")} hint={t("fields.sourceActHint")}>
              <TextInput
                value={form.source_act}
                onChange={(v) => setForm({ ...form, source_act: v })}
              />
            </Field>
          </div>

          <fieldset className="mt-3">
            <legend className="text-xs text-foreground-muted">{t("fields.requiredDocs")}</legend>
            <div className="mt-2 flex flex-wrap gap-3">
              {DOC_KINDS.map((kind) => (
                <label key={kind} className="flex items-center gap-2 text-sm text-foreground">
                  <input
                    type="checkbox"
                    checked={form.required_docs.includes(kind)}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        required_docs: e.target.checked
                          ? [...form.required_docs, kind]
                          : form.required_docs.filter((d) => d !== kind),
                      })
                    }
                    className="rounded border-border bg-background"
                  />
                  {t(`docKind.${kind}`)}
                </label>
              ))}
            </div>
          </fieldset>

          {formError && <p className="mt-3 text-sm text-red-400">{formError}</p>}

          <div className="mt-4 flex gap-2">
            <button
              type="button"
              disabled={save.isPending}
              onClick={() => save.mutate(toPayload(form))}
              className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
            >
              {t("save")}
            </button>
            <button
              type="button"
              onClick={() => {
                setForm(null);
                setEditing(null);
                setFormError(null);
              }}
              className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary"
            >
              {t("cancel")}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Turn an API failure into a sentence: the 409 says exactly what collided. */
function reasonOf(err: unknown, t: (key: string) => string): string {
  const detail = (err as { body?: { detail?: unknown } })?.body?.detail;
  if (detail === "substance_exists") return t("errors.exists");
  if (typeof detail === "string") return detail;
  return err instanceof Error ? err.message : t("error");
}

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-foreground-muted">
        {label}
        {required ? " *" : ""}
      </span>
      {children}
      {hint ? <span className="text-xs text-foreground-muted opacity-70">{hint}</span> : null}
    </label>
  );
}

function TextInput({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <input
      type="text"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent disabled:opacity-50"
    />
  );
}
