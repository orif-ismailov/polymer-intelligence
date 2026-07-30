import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { Button, FormField, Input, Select } from "@/shared/ui";
import type { SelectOption } from "@/shared/ui";
import { cn } from "@/shared/lib";

import {
  EXPORT_COUNTRY_OPTIONS,
  ISO_OPTIONS,
  MAIN_PRODUCT_OPTIONS,
  MARKET_OPTIONS,
  PRODUCTION_TYPES,
  foundationYearOptions,
  type MarketOption,
} from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { isProductionValid } from "../model/validation";

interface StepProductionProps {
  onNext: () => void;
  onBack: () => void;
}

/** Manufacturer step 3 — production facts from companys_list.jpeg. */
export function StepProduction({ onNext, onBack }: StepProductionProps) {
  const { t } = useTranslation();
  const manufacturer = useWizardDraft((s) => s.manufacturer);
  const setManufacturer = useWizardDraft((s) => s.setManufacturer);
  const [submitted, setSubmitted] = useState(false);
  const valid = isProductionValid(manufacturer);

  const productionTypeOptions: SelectOption[] = PRODUCTION_TYPES.map((value) => ({
    value,
    label: t(`wizard.production.types.${value}`),
  }));
  const productOptions: SelectOption[] = MAIN_PRODUCT_OPTIONS.map((value) => ({
    value,
    label: t(`wizard.production.products.${value}`),
  }));
  const isoOptions: SelectOption[] = ISO_OPTIONS.map((value) => ({
    value,
    label: t(`wizard.production.iso.${value}`),
  }));
  const yearOptions: SelectOption[] = foundationYearOptions().map((y) => ({
    value: String(y),
    label: String(y),
  }));
  const countryOptions: SelectOption[] = EXPORT_COUNTRY_OPTIONS.map((value) => ({
    value,
    label: t(`wizard.production.countries.${value}`),
  }));

  function toggleMarket(market: MarketOption): void {
    const has = manufacturer.markets.includes(market);
    const markets = has
      ? manufacturer.markets.filter((m) => m !== market)
      : [...manufacturer.markets, market];
    setManufacturer({
      markets,
      export_countries: markets.includes("export") ? manufacturer.export_countries : [],
    });
  }

  function toggleExportCountry(code: string): void {
    const has = manufacturer.export_countries.includes(code);
    setManufacturer({
      export_countries: has
        ? manufacturer.export_countries.filter((c) => c !== code)
        : [...manufacturer.export_countries, code],
    });
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    setSubmitted(true);
    if (valid) onNext();
  }

  return (
    <form className="space-y-6" onSubmit={handleSubmit} noValidate>
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.production.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.production.subtitle")}</p>
      </div>

      <div className="space-y-5">
        <FormField
          label={t("wizard.production.fields.productionType")}
          required
          error={
            submitted && !manufacturer.production_type
              ? t("wizard.production.required")
              : null
          }
        >
          {({ id, required }) => (
            <Select
              id={id}
              aria-required={required}
              options={productionTypeOptions}
              placeholder={t("wizard.production.selectPlaceholder")}
              value={manufacturer.production_type}
              onChange={(e) => setManufacturer({ production_type: e.target.value })}
            />
          )}
        </FormField>

        <FormField
          label={t("wizard.production.fields.mainProducts")}
          required
          error={
            submitted && !manufacturer.main_products ? t("wizard.production.required") : null
          }
        >
          {({ id, required }) => (
            <Select
              id={id}
              aria-required={required}
              options={productOptions}
              placeholder={t("wizard.production.selectPlaceholder")}
              value={manufacturer.main_products}
              onChange={(e) => setManufacturer({ main_products: e.target.value })}
            />
          )}
        </FormField>

        <FormField
          label={t("wizard.production.fields.annualCapacity")}
          required
          error={
            submitted && !manufacturer.annual_capacity_tons.trim()
              ? t("wizard.production.required")
              : null
          }
        >
          {({ id, required }) => (
            <Input
              id={id}
              aria-required={required}
              inputMode="decimal"
              value={manufacturer.annual_capacity_tons}
              trailing={<span className="text-xs text-text-muted">{t("wizard.units.tonsPerYear")}</span>}
              onChange={(e) => setManufacturer({ annual_capacity_tons: e.target.value })}
            />
          )}
        </FormField>

        <FormField
          label={t("wizard.production.fields.productionLines")}
          required
          error={
            submitted && !manufacturer.production_lines.trim()
              ? t("wizard.production.required")
              : null
          }
        >
          {({ id, required }) => (
            <Input
              id={id}
              aria-required={required}
              inputMode="numeric"
              value={manufacturer.production_lines}
              onChange={(e) =>
                setManufacturer({ production_lines: e.target.value.replace(/\D+/g, "") })
              }
            />
          )}
        </FormField>

        <FormField
          label={t("wizard.production.fields.employees")}
          required
          error={
            submitted && !manufacturer.employees.trim() ? t("wizard.production.required") : null
          }
        >
          {({ id, required }) => (
            <Input
              id={id}
              aria-required={required}
              inputMode="numeric"
              value={manufacturer.employees}
              onChange={(e) =>
                setManufacturer({ employees: e.target.value.replace(/\D+/g, "") })
              }
            />
          )}
        </FormField>

        <FormField label={t("wizard.production.fields.markets")} required>
          {() => (
            <div className="flex flex-wrap gap-2" role="group" aria-label={t("wizard.production.fields.markets")}>
              {MARKET_OPTIONS.map((market) => {
                const active = manufacturer.markets.includes(market);
                return (
                  <button
                    key={market}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleMarket(market)}
                    className={cn(
                      "rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                      active
                        ? "border-brand bg-brand-soft text-text"
                        : "border-border bg-surface text-text-muted hover:border-brand-line",
                    )}
                  >
                    {t(`wizard.production.markets.${market}`)}
                  </button>
                );
              })}
            </div>
          )}
        </FormField>

        {manufacturer.markets.includes("export") ? (
          <FormField
            label={t("wizard.production.fields.exportCountries")}
            required
            error={
              submitted && manufacturer.export_countries.length === 0
                ? t("wizard.production.exportCountriesRequired")
                : null
            }
          >
            {() => (
              <div className="flex flex-wrap gap-2">
                {countryOptions.map((opt) => {
                  const active = manufacturer.export_countries.includes(opt.value);
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggleExportCountry(opt.value)}
                      className={cn(
                        "rounded-md border px-3 py-1.5 text-sm transition-colors",
                        active
                          ? "border-brand bg-brand-soft text-text"
                          : "border-border bg-surface text-text-muted hover:border-brand-line",
                      )}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            )}
          </FormField>
        ) : null}

        <FormField
          label={t("wizard.production.fields.foundedYear")}
          required
          error={
            submitted && !manufacturer.founded_year ? t("wizard.production.required") : null
          }
        >
          {({ id, required }) => (
            <Select
              id={id}
              aria-required={required}
              options={yearOptions}
              placeholder={t("wizard.production.yearPlaceholder")}
              value={manufacturer.founded_year}
              onChange={(e) => setManufacturer({ founded_year: e.target.value })}
            />
          )}
        </FormField>

        <FormField label={t("wizard.production.fields.iso")}>
          {({ id }) => (
            <Select
              id={id}
              options={isoOptions}
              placeholder={t("wizard.production.isoPlaceholder")}
              value={manufacturer.iso_certification}
              onChange={(e) => setManufacturer({ iso_certification: e.target.value })}
            />
          )}
        </FormField>
      </div>

      <div className="flex gap-3">
        <Button type="button" variant="ghost" size="lg" onClick={onBack} className="min-w-24">
          {t("common.back")}
        </Button>
        <Button type="submit" size="lg" disabled={!valid} className="flex-1" data-testid="wizard-next">
          {t("common.next")}
        </Button>
      </div>
    </form>
  );
}
