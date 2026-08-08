import { useMemo, useState } from "react";

import { useTranslation } from "react-i18next";

import { PRODUCT_OTHER, productLabel, productName, useProducts } from "@/entities/product";
import { coerceLang } from "@/shared/i18n";
import {
  BoxIcon,
  Button,
  ChevronRightIcon,
  FormField,
  Input,
  PenLineIcon,
  SearchIcon,
  Select,
  type SelectOption,
} from "@/shared/ui";

import { COUNTED_STEPS, STEP_PRODUCT } from "../model/constants";
import { useRequestDraft } from "../model/draftStore";
import { isProductChosen } from "../model/validation";
import { StepNav } from "./StepNav";

interface StepProductProps {
  onNext: () => void;
}

/**
 * Sheet 1 — «Выберите продукт».
 *
 * Search + category filter over the catalog, a «Недавние продукты» list (the
 * catalog itself until we have a real recent-products API), and a manual-entry
 * escape hatch for grades that are not in the book.
 */
export function StepProduct({ onNext }: StepProductProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const draft = useRequestDraft((s) => s.draft);
  const setField = useRequestDraft((s) => s.setField);
  const patch = useRequestDraft((s) => s.patch);
  const products = useProducts();
  const [manualOpen, setManualOpen] = useState(draft.productChoice === PRODUCT_OTHER);
  const [touched, setTouched] = useState(false);

  const categories = useMemo(() => {
    const set = new Set<string>();
    for (const p of products.data ?? []) {
      if (p.category) set.add(p.category);
    }
    return [...set].sort();
  }, [products.data]);

  const categoryOptions: SelectOption[] = [
    { value: "", label: t("requestWizard.product.allCategories") },
    // Translated with the stored value as fallback — the DB vocabulary is
    // open-ended and a raw value still beats a raw i18n key.
    ...categories.map((c) => ({ value: c, label: t(`productCategory.${c}`, c) })),
  ];

  const filtered = useMemo(() => {
    const q = draft.searchQuery.trim().toLowerCase();
    return (products.data ?? []).filter((p) => {
      if (draft.categoryFilter && p.category !== draft.categoryFilter) return false;
      if (!q) return true;
      const hay = `${productName(p, lang)} ${p.code} ${p.category}`.toLowerCase();
      return hay.includes(q);
    });
  }, [products.data, draft.searchQuery, draft.categoryFilter, lang]);

  // Cap the list so a phone never scrolls through the entire catalog on sheet 1.
  const visible = filtered.slice(0, 12);

  function pickProduct(id: number, label: string, code: string): void {
    setManualOpen(false);
    patch({
      productChoice: String(id),
      productLabel: label,
      polymerType: code,
      productText: "",
    });
  }

  function openManual(): void {
    setManualOpen(true);
    patch({
      productChoice: PRODUCT_OTHER,
      productLabel: "",
      polymerType: "",
    });
  }

  function handleNext(): void {
    setTouched(true);
    if (isProductChosen(draft)) onNext();
  }

  const missing = touched && !isProductChosen(draft);
  const selectedId = draft.productChoice !== PRODUCT_OTHER ? draft.productChoice : "";

  return (
    <div className="space-y-5" data-testid="request-wizard-step-1">
      <header>
        <p className="num text-xs text-text-muted">
          {t("requestWizard.stepOf", { current: STEP_PRODUCT, total: COUNTED_STEPS })}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-text">
          {t("requestWizard.product.title")}
        </h2>
        <p className="mt-1 text-sm text-text-muted">{t("requestWizard.subtitle")}</p>
      </header>

      <div className="relative">
        <span className="pointer-events-none absolute inset-y-0 start-3 flex items-center text-text-subtle">
          <SearchIcon size={16} />
        </span>
        <Input
          value={draft.searchQuery}
          onChange={(e) => setField("searchQuery", e.target.value)}
          placeholder={t("requestWizard.product.searchPlaceholder")}
          className="ps-9"
          aria-label={t("common.search")}
          data-testid="request-wizard-search"
        />
      </div>

      <FormField label={t("requestWizard.product.category")}>
        {({ id }) => (
          <Select
            id={id}
            options={categoryOptions}
            value={draft.categoryFilter}
            onChange={(e) => setField("categoryFilter", e.target.value)}
          />
        )}
      </FormField>

      <div>
        <h3 className="mb-2 text-sm font-medium text-text-muted">
          {t("requestWizard.product.recent")}
        </h3>
        <ul className="divide-y divide-border overflow-hidden rounded-md border border-border bg-surface">
          {visible.map((p) => {
            const label = productLabel(p, lang);
            const selected = selectedId === String(p.id);
            return (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => pickProduct(p.id, label, p.code)}
                  className={
                    "flex w-full items-center gap-3 px-3 py-3 text-start transition-colors " +
                    (selected
                      ? "bg-brand-soft/40"
                      : "hover:bg-surface-2")
                  }
                  data-testid={`request-wizard-product-${p.id}`}
                  data-selected={selected || undefined}
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-surface-inset text-text-muted">
                    <BoxIcon size={18} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-text">
                      {productName(p, lang)}
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-text-muted">
                      {p.code}
                      {p.category
                        ? ` · ${t(`productCategory.${p.category}`, p.category)}`
                        : ""}
                    </span>
                  </span>
                  <ChevronRightIcon size={16} className="shrink-0 text-text-subtle" />
                </button>
              </li>
            );
          })}
          {visible.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-text-muted">
              {t("requestWizard.product.empty")}
            </li>
          ) : null}
        </ul>
      </div>

      {manualOpen ? (
        <div className="space-y-3 rounded-md border border-border bg-surface p-4">
          <FormField
            label={t("requestWizard.product.manualName")}
            required
            error={missing && !draft.productText.trim() ? t("requestWizard.product.nameRequired") : null}
          >
            {({ id, invalid }) => (
              <Input
                id={id}
                value={draft.productText}
                onChange={(e) => setField("productText", e.target.value)}
                invalid={invalid}
                placeholder={t("requestWizard.product.manualNamePlaceholder")}
                data-testid="request-wizard-product-text"
              />
            )}
          </FormField>
          <FormField
            label={t("requestWizard.product.manualGrade")}
            required
            error={missing && !draft.gradeText.trim() ? t("requestWizard.product.gradeRequired") : null}
          >
            {({ id, invalid }) => (
              <Input
                id={id}
                value={draft.gradeText}
                onChange={(e) => setField("gradeText", e.target.value)}
                invalid={invalid}
                placeholder={t("requestWizard.product.manualGradePlaceholder")}
                data-testid="request-wizard-grade"
              />
            )}
          </FormField>
        </div>
      ) : (
        <Button
          variant="outline"
          fullWidth
          size="lg"
          onClick={openManual}
          data-testid="request-wizard-manual"
        >
          <PenLineIcon size={16} />
          {t("requestWizard.product.manual")}
        </Button>
      )}

      {missing && !manualOpen ? (
        <p className="text-sm text-danger">{t("requestWizard.product.pickRequired")}</p>
      ) : null}

      <StepNav onNext={handleNext} />
    </div>
  );
}
