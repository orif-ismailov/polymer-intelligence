import { useState } from "react";

import { useTranslation } from "react-i18next";

import { PRODUCT_OTHER, productLabel, useProducts } from "@/entities/product";
import { coerceLang } from "@/shared/i18n";
import { countryName } from "@/shared/lib";
import { Alert, FormField, Input, Select, StepPanel } from "@/shared/ui";
import type { SelectOption } from "@/shared/ui";

import {
  COUNTED_STEPS,
  MANUFACTURERS,
  ORIGIN_COUNTRIES,
  OTHER_OPTION,
  STEP_BASICS,
} from "../model/constants";
import { useOfferDraft } from "../model/draftStore";
import { isProductNamed } from "../model/validation";
import { PhotoGrid } from "./PhotoGrid";
import { StepNav } from "./StepNav";

interface StepBasicsProps {
  companyId: number;
  onNext: () => void;
}

/** Sheet 1 — «Основная информация». */
export function StepBasics({ companyId, onNext }: StepBasicsProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const draft = useOfferDraft((s) => s.draft);
  const setField = useOfferDraft((s) => s.setField);
  const products = useProducts();
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  /*
   * Manufacturer is a select on the mockup («Sibur ▾»). Free text only appears
   * when the seller picks «Другое» — same escape hatch as the product name.
   * An offer reopened with a maker outside the curated list lands on «Другое»
   * with the stored value in the manual field, rather than being wiped.
   */
  const manufacturerKnown = (MANUFACTURERS as readonly string[]).includes(draft.manufacturer);
  const [manufacturerOther, setManufacturerOther] = useState(
    () => (manufacturerKnown || draft.manufacturer === "" ? false : true),
  );

  const isOther = draft.productChoice === PRODUCT_OTHER;

  /*
   * The catalog, then «Другое» — the Mini App's shape, and the reason the field
   * can be a select at all: a seller whose grade is not in the catalog types it
   * instead of being turned away.
   */
  const productOptions: SelectOption[] = [
    ...(products.data ?? []).map((p) => ({ value: String(p.id), label: productLabel(p, lang) })),
    { value: PRODUCT_OTHER, label: t("offerWizard.basics.productOther") },
  ];

  /*
   * Country names come from `Intl.DisplayNames`, so the list is codes only; an
   * offer already carrying a code outside the list keeps it as its own option
   * rather than being silently re-pointed at the first one on the next save.
   */
  const countryOptions: SelectOption[] = [
    ...ORIGIN_COUNTRIES.map((code) => ({ value: code, label: countryName(code, lang) })),
    ...(draft.originCountry && !(ORIGIN_COUNTRIES as readonly string[]).includes(draft.originCountry)
      ? [{ value: draft.originCountry, label: countryName(draft.originCountry, lang) }]
      : []),
  ];

  /*
   * «Категория» is the polymer family — «Полипропилен (PP)» — not the product
   * row itself. Same catalog, different field.
   */
  const categoryOptions: SelectOption[] = [
    { value: "", label: t("offerWizard.basics.categoryUnset") },
    ...(products.data ?? []).map((p) => ({
      value: productLabel(p, lang),
      label: productLabel(p, lang),
    })),
    ...(draft.category &&
    !(products.data ?? []).some((p) => productLabel(p, lang) === draft.category)
      ? [{ value: draft.category, label: draft.category }]
      : []),
  ];

  const manufacturerOptions: SelectOption[] = [
    ...MANUFACTURERS.map((name) => ({ value: name, label: name })),
    { value: OTHER_OPTION, label: t("offerWizard.basics.manufacturerOther") },
  ];

  const manufacturerSelectValue = manufacturerOther
    ? OTHER_OPTION
    : manufacturerKnown
      ? draft.manufacturer
      : "";

  const nameMissing = touched && !isProductNamed(draft);

  function handleProductChange(value: string): void {
    setField("productChoice", value);
    /*
     * Picking a catalog row fills «Категория» with the same family the mockup
     * shows next to the name («Полипропилен (PP)»), unless the seller already
     * chose one — do not overwrite a deliberate pick.
     */
    if (value === PRODUCT_OTHER || draft.category) return;
    const row = (products.data ?? []).find((p) => String(p.id) === value);
    if (row) setField("category", productLabel(row, lang));
  }

  function handleManufacturerChange(value: string): void {
    if (value === OTHER_OPTION) {
      setManufacturerOther(true);
      if (manufacturerKnown) setField("manufacturer", "");
      return;
    }
    setManufacturerOther(false);
    setField("manufacturer", value);
  }

  function handleNext(): void {
    setTouched(true);
    if (isProductNamed(draft)) onNext();
  }

  return (
    <StepPanel
      step={STEP_BASICS}
      title={t("offerWizard.basics.title")}
      counter={t("offerWizard.stepOf", { current: STEP_BASICS, total: COUNTED_STEPS })}
      data-testid="offer-wizard-step-1"
    >
      <h3 className="mb-4 text-lg font-semibold text-text">{t("offerWizard.basics.heading")}</h3>

      <div className="space-y-4">
        <FormField
          label={t("offerWizard.basics.productName")}
          required
          error={nameMissing && !isOther ? t("offerWizard.basics.productRequired") : null}
        >
          {({ id, invalid, describedBy }) => (
            <Select
              id={id}
              options={productOptions}
              placeholder={t("offerWizard.basics.productPlaceholder")}
              value={draft.productChoice}
              invalid={invalid}
              aria-describedby={describedBy}
              disabled={products.isLoading}
              onChange={(e) => handleProductChange(e.target.value)}
              data-testid="offer-wizard-product"
            />
          )}
        </FormField>

        {/* «Другое»: the catalog does not carry it, so the seller names it. */}
        {isOther ? (
          <FormField
            label={t("offerWizard.basics.productManual")}
            required
            error={nameMissing ? t("offerWizard.basics.productManualRequired") : null}
          >
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                value={draft.productText}
                invalid={invalid}
                aria-describedby={describedBy}
                placeholder={t("offerWizard.basics.productManualPlaceholder")}
                onChange={(e) => setField("productText", e.target.value)}
                data-testid="offer-wizard-product-text"
              />
            )}
          </FormField>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label={t("offerWizard.basics.cas")}>
            {({ id }) => (
              <Input
                id={id}
                value={draft.casNumber}
                placeholder="9003-07-0"
                onChange={(e) => setField("casNumber", e.target.value)}
              />
            )}
          </FormField>
          <FormField label={t("offerWizard.basics.hs")}>
            {({ id }) => (
              <Input
                id={id}
                value={draft.hsCode}
                placeholder="3902.10.9000"
                onChange={(e) => setField("hsCode", e.target.value)}
              />
            )}
          </FormField>
        </div>

        <FormField label={t("offerWizard.basics.manufacturer")}>
          {({ id }) => (
            <Select
              id={id}
              options={manufacturerOptions}
              placeholder={t("offerWizard.basics.manufacturerPlaceholder")}
              value={manufacturerSelectValue}
              onChange={(e) => handleManufacturerChange(e.target.value)}
              data-testid="offer-wizard-manufacturer"
            />
          )}
        </FormField>

        {manufacturerOther ? (
          <FormField label={t("offerWizard.basics.manufacturerManual")}>
            {({ id }) => (
              <Input
                id={id}
                value={draft.manufacturer}
                placeholder={t("offerWizard.basics.manufacturerPlaceholder")}
                onChange={(e) => setField("manufacturer", e.target.value)}
                data-testid="offer-wizard-manufacturer-text"
              />
            )}
          </FormField>
        ) : null}

        <FormField label={t("offerWizard.basics.originCountry")}>
          {({ id }) => (
            <Select
              id={id}
              options={countryOptions}
              value={draft.originCountry}
              onChange={(e) => setField("originCountry", e.target.value)}
            />
          )}
        </FormField>

        <FormField label={t("offerWizard.basics.category")}>
          {({ id }) => (
            <Select
              id={id}
              options={categoryOptions}
              value={draft.category}
              disabled={products.isLoading}
              onChange={(e) => setField("category", e.target.value)}
            />
          )}
        </FormField>

        <div>
          <p className="mb-1.5 text-sm font-medium text-text">
            {t("offerWizard.basics.photos")}
          </p>
          <PhotoGrid companyId={companyId} onError={setPhotoError} />
          {photoError ? (
            <p role="alert" className="mt-2 text-xs text-danger">
              {photoError}
            </p>
          ) : null}
        </div>
      </div>

      {products.isError ? (
        <Alert tone="warning" className="mt-4" title={t("offerWizard.basics.catalogUnavailable")}>
          {t("offerWizard.basics.catalogUnavailableBody")}
        </Alert>
      ) : null}

      <StepNav onNext={handleNext} />
    </StepPanel>
  );
}
