import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/shared/api";
import { Button, FormField, Input, Select } from "@/shared/ui";

import { ikpuApi } from "../model/api";

/** 17 digits — the tasnif.soliq.uz code format. */
const IKPU_CODE = /^\d{17}$/;

/**
 * The ЭСФ `Origin` — how THIS seller came by the goods.
 *
 * Didox returns `origin: null` on every row (their own docs show it too), and it
 * could not be otherwise: the same code is own production for a factory and
 * resale for a trader. So it is the seller's answer, asked once here, and the
 * offer cannot be published without it — `ck_offer_ikpu_complete` says the same
 * thing in the schema.
 */
const ORIGINS = [1, 2, 3, 4] as const;
import type { IkpuRow } from "../model/api";

export interface IkpuValue {
  code: string;
  name: string;
  packageCode: string;
  packageName: string;
  origin: number | null;
}

interface IkpuPickerProps {
  companyId: number;
  value: IkpuValue | null;
  onChange: (value: IkpuValue | null) => void;
}

/**
 * Pick the ИКПУ (tax classification) for an offer's goods.
 *
 * This code rides on every «Договор НК» and ЭСФ the offer backs, and both reach
 * my.soliq.uz, so it is chosen ONCE here rather than re-answered per contract.
 *
 * **The search only covers codes this company has already declared.** Didox's
 * partner API has no global tasnif search — verified live — so an empty result is
 * the NORMAL first experience, not a dead end: the seller takes their code from
 * tasnif.soliq.uz and adds it, which both declares it to Didox and makes it
 * findable here afterwards. The "add by code" path is therefore the primary
 * action, and search is how you re-find something you already declared.
 *
 * Three failure states stay distinct because they need different things from the
 * seller: **no Didox session** (409, one click), **Didox unavailable** (503,
 * nothing they can do), and **no matches** — which is a real answer and must not
 * be dressed up as an error.
 */
export function IkpuPicker({ companyId, value, onChange }: IkpuPickerProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<IkpuRow[] | null>(null);
  /**
   * The chosen row itself, NOT derived from `rows`.
   *
   * `rows` is cleared on pick and is gone entirely after a remount, so deriving
   * the row from it means the package `Select` below never renders for a code
   * that has several packages — the seller would be stuck with whichever one
   * happened to be first, on a field that reaches the tax authority.
   */
  const [picked, setPicked] = useState<IkpuRow | null>(null);
  const [error, setError] = useState<"session" | "unavailable" | "failed" | "badCode" | null>(null);
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);

  async function search() {
    const term = query.trim();
    if (!term) return;
    setBusy(true);
    setError(null);
    try {
      setRows(await ikpuApi.search(companyId, term));
      setSearched(true);
    } catch (err) {
      setRows(null);
      if (err instanceof ApiError && err.status === 409) setError("session");
      else if (err instanceof ApiError && err.status === 503) setError("unavailable");
      else setError("failed");
    } finally {
      setBusy(false);
    }
  }

  function choose(row: IkpuRow) {
    const [first] = row.packages;
    onChange({
      code: row.class_code,
      name: row.name ?? row.class_code,
      packageCode: first?.code ?? "",
      packageName: first?.name ?? "",
      origin: row.origin_id,
    });
    setPicked(row);
    setRows(null);
  }

  /**
   * Declare a code the company has not used before.
   *
   * Bind FIRST, then read it back: the bound row is what carries the packages and
   * the `origin`, and both end up on every document — guessing either would put a
   * wrong value on something that reaches the tax authority.
   */
  async function addByCode() {
    const code = query.trim();
    if (!IKPU_CODE.test(code)) {
      setError("badCode");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await ikpuApi.bind(companyId, code);
      const [row] = await ikpuApi.search(companyId, code);
      if (!row) {
        setError("failed");
        return;
      }
      choose(row);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setError("session");
      else if (err instanceof ApiError && err.status === 503) setError("unavailable");
      else setError("failed");
    } finally {
      setBusy(false);
    }
  }

  /**
   * A code can arrive already chosen — editing an offer, or a remount — with no
   * search behind it. Load its packages so the seller can still change the one
   * that goes on the documents.
   */
  useEffect(() => {
    const code = value?.code;
    if (!code || picked?.class_code === code) return;
    let cancelled = false;
    void ikpuApi
      .packages(companyId, code)
      .then((packages) => {
        if (cancelled) return;
        setPicked({
          class_code: code,
          name: value?.name ?? code,
          origin_id: value?.origin ?? null,
          origin_name: null,
          use_package: packages.length > 0,
          packages,
        });
      })
      // Silent on purpose: the code is already chosen and valid. Failing to load
      // its package LIST costs the ability to change one, not the field itself.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [companyId, value?.code, value?.name, value?.origin, picked?.class_code]);

  const chosen = picked?.class_code === value?.code ? picked : null;
  const looksLikeCode = IKPU_CODE.test(query.trim());

  return (
    <div className="space-y-3">
      <FormField label={t("ikpu.label")} hint={t("ikpu.hint")}>
        {({ id }) => (
          <div className="flex gap-2">
            <Input
              id={id}
              value={query}
              placeholder={t("ikpu.placeholder")}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void search();
                }
              }}
              data-testid="ikpu-query"
            />
            <Button
              type="button"
              variant="secondary"
              disabled={busy || !query.trim()}
              onClick={() => void search()}
              data-testid="ikpu-search"
            >
              {t("ikpu.search")}
            </Button>
          </div>
        )}
      </FormField>

      {error === "session" && (
        <p className="text-sm text-warning" data-testid="ikpu-session">
          {t("ikpu.errors.session")}
        </p>
      )}
      {error === "unavailable" && (
        <p className="text-sm text-warning" data-testid="ikpu-unavailable">
          {t("ikpu.errors.unavailable")}
        </p>
      )}
      {error === "failed" && <p className="text-sm text-danger">{t("ikpu.errors.failed")}</p>}
      {error === "badCode" && (
        <p className="text-sm text-danger" data-testid="ikpu-badcode">{t("ikpu.errors.badCode")}</p>
      )}

      {/* An empty result is the normal FIRST experience — the search only sees
          codes this company already declared — so it offers the way forward
          rather than reading as a dead end. */}
      {searched && rows?.length === 0 && (
        <div className="space-y-2" data-testid="ikpu-empty">
          <p className="text-sm text-text-muted">{t("ikpu.emptyAdd")}</p>
          <Button
            type="button"
            variant="secondary"
            disabled={busy || !looksLikeCode}
            onClick={() => void addByCode()}
            data-testid="ikpu-add"
          >
            {t("ikpu.add", { code: query.trim() })}
          </Button>
          {!looksLikeCode && (
            <p className="text-xs text-text-muted">{t("ikpu.codeHint")}</p>
          )}
        </div>
      )}

      {rows && rows.length > 0 && (
        <ul className="space-y-1" data-testid="ikpu-results">
          {rows.map((row) => (
            <li key={row.class_code}>
              <button
                type="button"
                className="w-full rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-surface-2"
                onClick={() => choose(row)}
              >
                <span className="num text-text-muted">{row.class_code}</span>
                <span className="ml-2">{row.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {value && (
        <div className="rounded-md border border-border p-3 text-sm" data-testid="ikpu-chosen">
          <div>
            <span className="num text-text-muted">{value.code}</span>
            <span className="ml-2">{value.name}</span>
          </div>
          {/* Packages come WITH the code — a package that is not on its list is
              rejected by the roaming centre, so this is a select, never free text. */}
          {chosen && chosen.packages.length > 1 && (
            <FormField label={t("ikpu.package")}>
              {({ id }) => (
                <Select
                  id={id}
                  value={value.packageCode}
                  options={chosen.packages.map((p) => ({ value: p.code, label: p.name }))}
                  onChange={(e) => {
                    const pkg = chosen.packages.find((p) => p.code === e.target.value);
                    onChange({
                      ...value,
                      packageCode: pkg?.code ?? "",
                      packageName: pkg?.name ?? "",
                    });
                  }}
                />
              )}
            </FormField>
          )}
          <p className="mt-1 text-xs text-text-muted">
            {t("ikpu.chosenPackage", { name: value.packageName || "—" })}
          </p>

          {/* Origin is the seller's own answer — Didox never supplies it. */}
          <FormField label={t("ikpu.origin")} hint={t("ikpu.originHint")}>
            {({ id }) => (
              <Select
                id={id}
                value={value.origin == null ? "" : String(value.origin)}
                options={[
                  { value: "", label: t("ikpu.originPlaceholder") },
                  ...ORIGINS.map((code) => ({
                    value: String(code),
                    label: t(`ikpu.origins.${code}`),
                  })),
                ]}
                onChange={(e) =>
                  onChange({ ...value, origin: e.target.value ? Number(e.target.value) : null })
                }
                data-testid="ikpu-origin"
              />
            )}
          </FormField>
          {value.origin == null && (
            <p className="mt-1 text-xs text-warning" data-testid="ikpu-origin-missing">
              {t("ikpu.originRequired")}
            </p>
          )}
          <Button
            type="button"
            variant="ghost"
            className="mt-2"
            onClick={() => onChange(null)}
            data-testid="ikpu-clear"
          >
            {t("common.clear")}
          </Button>
        </div>
      )}
    </div>
  );
}
