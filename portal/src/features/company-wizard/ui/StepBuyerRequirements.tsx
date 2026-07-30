import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { Button, Checkbox, FormField, Input } from "@/shared/ui";
import { cn } from "@/shared/lib";

import {
  ADDITIONAL_REQUIREMENT_KEYS,
  FINANCIAL_REQUIREMENT_KEYS,
  type AdditionalRequirementKey,
  type FinancialRequirementKey,
} from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { isBuyerRequirementsValid } from "../model/validation";

interface StepBuyerRequirementsProps {
  onNext: () => void;
  onBack: () => void;
}

/** Manufacturer buyer-requirements step from companys_list.jpeg. */
export function StepBuyerRequirements({ onNext, onBack }: StepBuyerRequirementsProps) {
  const { t } = useTranslation();
  const manufacturer = useWizardDraft((s) => s.manufacturer);
  const setManufacturer = useWizardDraft((s) => s.setManufacturer);
  const [submitted, setSubmitted] = useState(false);
  const valid = isBuyerRequirementsValid(manufacturer);

  function toggleFinancial(key: FinancialRequirementKey): void {
    setManufacturer({
      financial_requirements: {
        ...manufacturer.financial_requirements,
        [key]: !manufacturer.financial_requirements[key],
      },
    });
  }

  function toggleAdditional(key: AdditionalRequirementKey): void {
    const has = manufacturer.additional_requirements.includes(key);
    setManufacturer({
      additional_requirements: has
        ? manufacturer.additional_requirements.filter((k) => k !== key)
        : [...manufacturer.additional_requirements, key],
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
        <h2 className="text-lg font-semibold text-text">{t("wizard.buyerReqs.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.buyerReqs.subtitle")}</p>
      </div>

      <div className="space-y-5">
        <div>
          <h3 className="mb-3 text-sm font-semibold text-text">
            {t("wizard.buyerReqs.volumeSection")}
          </h3>
          <div className="space-y-4">
            <FormField
              label={t("wizard.buyerReqs.fields.moq")}
              required
              error={
                submitted && !manufacturer.moq_tons.trim()
                  ? t("wizard.buyerReqs.moqRequired")
                  : null
              }
            >
              {({ id, required }) => (
                <Input
                  id={id}
                  aria-required={required}
                  inputMode="decimal"
                  value={manufacturer.moq_tons}
                  trailing={
                    <span className="text-xs text-text-muted">{t("wizard.units.tons")}</span>
                  }
                  onChange={(e) => setManufacturer({ moq_tons: e.target.value })}
                />
              )}
            </FormField>

            <FormField label={t("wizard.buyerReqs.fields.minAnnual")}>
              {({ id }) => (
                <Input
                  id={id}
                  inputMode="decimal"
                  value={manufacturer.min_annual_volume_tons}
                  trailing={
                    <span className="text-xs text-text-muted">{t("wizard.units.tons")}</span>
                  }
                  onChange={(e) => setManufacturer({ min_annual_volume_tons: e.target.value })}
                />
              )}
            </FormField>
          </div>
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold text-text">
            {t("wizard.buyerReqs.financialSection")}
          </h3>
          <ul className="divide-y divide-border rounded-md border border-border">
            {FINANCIAL_REQUIREMENT_KEYS.map((key) => {
              const on = manufacturer.financial_requirements[key];
              return (
                <li key={key} className="flex items-center justify-between gap-3 px-3 py-3">
                  <span className="text-sm text-text">{t(`wizard.buyerReqs.financial.${key}`)}</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={on}
                    onClick={() => toggleFinancial(key)}
                    className={cn(
                      "relative h-6 w-11 shrink-0 rounded-full transition-colors",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                      on ? "bg-brand" : "bg-surface-inset border border-border",
                    )}
                  >
                    <span
                      className={cn(
                        "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-bg transition-transform",
                        on && "translate-x-5",
                      )}
                    />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold text-text">
            {t("wizard.buyerReqs.additionalSection")}
          </h3>
          <div className="space-y-2">
            {ADDITIONAL_REQUIREMENT_KEYS.map((key) => (
              <Checkbox
                key={key}
                id={`buyer-req-${key}`}
                label={t(`wizard.buyerReqs.additional.${key}`)}
                checked={manufacturer.additional_requirements.includes(key)}
                onChange={() => toggleAdditional(key)}
              />
            ))}
          </div>
          {manufacturer.additional_requirements.includes("other") ? (
            <FormField label={t("wizard.buyerReqs.fields.otherDetail")} className="mt-3">
              {({ id }) => (
                <Input
                  id={id}
                  value={manufacturer.additional_other}
                  onChange={(e) => setManufacturer({ additional_other: e.target.value })}
                />
              )}
            </FormField>
          ) : null}
        </div>
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
