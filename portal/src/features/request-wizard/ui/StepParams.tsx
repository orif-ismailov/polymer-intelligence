import { useState } from "react";

import { useTranslation } from "react-i18next";

import { INCOTERMS, QTY_UNITS } from "@/shared/config";
import { coerceLang } from "@/shared/i18n";
import { countryName, cn } from "@/shared/lib";
import {
  CheckCircleOutlineIcon,
  FormField,
  Input,
  Select,
  type SelectOption,
} from "@/shared/ui";

import {
  COUNTED_STEPS,
  DEFAULT_DEST_COUNTRY,
  DELIVERY_BANDS,
  DEST_CITIES,
  DEST_COUNTRIES,
  OTHER_OPTION,
  PRICE_CURRENCIES,
  STEP_PARAMS,
  VALIDITY_OPTIONS,
} from "../model/constants";
import { useRequestDraft } from "../model/draftStore";
import { isParamsValid } from "../model/validation";
import { StepNav } from "./StepNav";

interface StepParamsProps {
  onNext: () => void;
  onBack: () => void;
}

/**
 * Sheet 2 — «Параметры запроса»: volume, target price, Incoterms, destination,
 * delivery timing tiles, validity.
 */
export function StepParams({ onNext, onBack }: StepParamsProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const draft = useRequestDraft((s) => s.draft);
  const setField = useRequestDraft((s) => s.setField);
  const [touched, setTouched] = useState(false);
  const [cityOther, setCityOther] = useState(draft.cityChoice === OTHER_OPTION);

  const unitOptions: SelectOption[] = QTY_UNITS.filter((u) => u !== "PCS").map((u) => ({
    value: u,
    label: u,
  }));

  const currencyOptions: SelectOption[] = PRICE_CURRENCIES.map((c) => ({
    value: c,
    label: `${c} / ${draft.volumeUnit || "MT"}`,
  }));

  const incotermOptions: SelectOption[] = INCOTERMS.filter((i) => i !== "unknown").map((i) => ({
    value: i,
    label: t(`requestWizard.params.incotermOpt.${i}`, { defaultValue: i }),
  }));

  const countryOptions: SelectOption[] = DEST_COUNTRIES.map((code) => ({
    value: code,
    label: countryName(code, lang),
  }));
  if (
    draft.destinationCountry &&
    !(DEST_COUNTRIES as readonly string[]).includes(draft.destinationCountry)
  ) {
    countryOptions.push({
      value: draft.destinationCountry,
      label: countryName(draft.destinationCountry, lang),
    });
  }

  const cityOptions: SelectOption[] = [
    ...DEST_CITIES.map((c) => ({ value: c, label: c })),
    { value: OTHER_OPTION, label: t("requestWizard.params.cityOther") },
  ];

  const validityOptions: SelectOption[] = VALIDITY_OPTIONS.map((d) => ({
    value: String(d),
    label: t("requestWizard.params.validityOpt", { days: d }),
  }));

  function handleCityChange(value: string): void {
    if (value === OTHER_OPTION) {
      setCityOther(true);
      setField("cityChoice", OTHER_OPTION);
      return;
    }
    setCityOther(false);
    setField("cityChoice", value);
  }

  function handleNext(): void {
    setTouched(true);
    if (isParamsValid(draft)) onNext();
  }

  const volumeMissing = touched && !(Number(draft.volume) > 0);

  return (
    <div className="space-y-5" data-testid="request-wizard-step-2">
      <header>
        <p className="num text-xs text-text-muted">
          {t("requestWizard.stepOf", { current: STEP_PARAMS, total: COUNTED_STEPS })}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-text">
          {t("requestWizard.params.title")}
        </h2>
      </header>

      <FormField
        label={t("requestWizard.params.volume")}
        required
        error={volumeMissing ? t("requestWizard.params.volumeRequired") : null}
      >
        {({ id, invalid }) => (
          <div className="flex gap-2">
            <Input
              id={id}
              inputMode="decimal"
              value={draft.volume}
              onChange={(e) => setField("volume", e.target.value)}
              invalid={invalid}
              className="flex-1"
              data-testid="request-wizard-volume"
            />
            <div className="w-24 shrink-0">
              <Select
                options={unitOptions}
                value={draft.volumeUnit}
                onChange={(e) => setField("volumeUnit", e.target.value)}
                aria-label={t("requestWizard.params.unit")}
              />
            </div>
          </div>
        )}
      </FormField>

      <FormField
        label={t("requestWizard.params.price")}
        hint={t("requestWizard.params.priceHint")}
      >
        {({ id }) => (
          <div className="flex gap-2">
            <Input
              id={id}
              inputMode="decimal"
              value={draft.targetPrice}
              onChange={(e) => setField("targetPrice", e.target.value)}
              className="flex-1"
              data-testid="request-wizard-price"
            />
            <div className="w-36 shrink-0">
              <Select
                options={currencyOptions}
                value={draft.currency}
                onChange={(e) => setField("currency", e.target.value)}
                aria-label={t("requestWizard.params.currency")}
              />
            </div>
          </div>
        )}
      </FormField>

      <FormField
        label={t("requestWizard.params.dealType")}
        hint={t("requestWizard.params.dealHint")}
      >
        {({ id }) => (
          <Select
            id={id}
            options={incotermOptions}
            value={draft.incoterms}
            onChange={(e) => setField("incoterms", e.target.value)}
            data-testid="request-wizard-incoterms"
          />
        )}
      </FormField>

      <FormField label={t("requestWizard.params.country")} required>
        {({ id }) => (
          <Select
            id={id}
            options={countryOptions}
            value={draft.destinationCountry || DEFAULT_DEST_COUNTRY}
            onChange={(e) => setField("destinationCountry", e.target.value)}
          />
        )}
      </FormField>

      <FormField label={t("requestWizard.params.city")}>
        {({ id }) => (
          <div className="space-y-2">
            <Select
              id={id}
              options={cityOptions}
              value={cityOther ? OTHER_OPTION : draft.cityChoice}
              onChange={(e) => handleCityChange(e.target.value)}
            />
            {cityOther ? (
              <Input
                value={draft.cityOther}
                onChange={(e) => setField("cityOther", e.target.value)}
                placeholder={t("requestWizard.params.cityPlaceholder")}
              />
            ) : null}
          </div>
        )}
      </FormField>

      <fieldset>
        <legend className="mb-2 text-sm font-medium text-text">
          {t("requestWizard.params.delivery")}
          <span className="ms-0.5 text-danger" aria-hidden="true">
            *
          </span>
        </legend>
        <div className="grid grid-cols-2 gap-2">
          {DELIVERY_BANDS.map((band) => {
            const checked = draft.deliveryBand === band.id;
            return (
              <label
                key={band.id}
                className={cn(
                  "relative flex cursor-pointer items-center justify-center rounded-md border px-3 py-3.5 text-center text-sm transition-colors",
                  "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-bg",
                  checked
                    ? "border-brand bg-brand-soft/30 font-medium text-brand"
                    : "border-border bg-surface-inset text-text-muted hover:border-border-strong",
                )}
                data-testid={`request-wizard-delivery-${band.id}`}
                data-checked={checked || undefined}
              >
                <input
                  type="radio"
                  name="delivery-band"
                  value={band.id}
                  checked={checked}
                  onChange={() => setField("deliveryBand", band.id)}
                  className="sr-only"
                />
                {t(`requestWizard.params.deliveryOpt.${band.id}`)}
                {checked ? (
                  <span className="absolute end-1.5 top-1.5 text-brand">
                    <CheckCircleOutlineIcon size={16} />
                  </span>
                ) : null}
              </label>
            );
          })}
        </div>
      </fieldset>

      <FormField label={t("requestWizard.params.validity")} required>
        {({ id }) => (
          <Select
            id={id}
            options={validityOptions}
            value={String(draft.validityDays)}
            onChange={(e) => setField("validityDays", Number(e.target.value))}
          />
        )}
      </FormField>

      <StepNav onNext={handleNext} onBack={onBack} />
    </div>
  );
}
