import { useState } from "react";

import { useTranslation } from "react-i18next";

import { DateInput, FormField, Input, Select, type SelectOption } from "@/shared/ui";

import { COUNTED_STEPS, RFQ_CURRENCIES, RFQ_INCOTERMS, RFQ_QTY_UNITS, STEP_BASIC } from "../model/constants";
import { isBasicValid, useFactoryRfqDraft } from "../model/draftStore";
import { StepNav } from "./StepNav";

interface StepBasicProps {
  onNext: () => void;
}

/** Sheet 1 — quantity, target price, Incoterms, destination port, delivery date. */
export function StepBasic({ onNext }: StepBasicProps) {
  const { t } = useTranslation();
  const draft = useFactoryRfqDraft((s) => s.draft);
  const setField = useFactoryRfqDraft((s) => s.setField);
  const [touched, setTouched] = useState(false);

  const unitOptions: SelectOption[] = RFQ_QTY_UNITS.map((u) => ({ value: u, label: u }));
  const currencyOptions: SelectOption[] = RFQ_CURRENCIES.map((c) => ({ value: c, label: c }));
  const incotermOptions: SelectOption[] = RFQ_INCOTERMS.map((i) => ({
    value: i,
    label: t(`requestWizard.params.incotermOpt.${i}`, { defaultValue: i }),
  }));

  function handleNext(): void {
    setTouched(true);
    if (isBasicValid(draft)) onNext();
  }

  const quantityMissing = touched && !(Number(draft.quantity) > 0);

  return (
    <div className="space-y-5" data-testid="factory-rfq-step-1">
      <header>
        <p className="num text-xs text-text-muted">
          {t("factoryRfq.stepOf", { current: STEP_BASIC, total: COUNTED_STEPS })}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-text">{t("factoryRfq.basic.title")}</h2>
      </header>

      <FormField
        label={t("factoryRfq.basic.quantity")}
        required
        error={quantityMissing ? t("factoryRfq.basic.quantityRequired") : null}
      >
        {({ id, invalid }) => (
          <div className="flex gap-2">
            <Input
              id={id}
              inputMode="decimal"
              value={draft.quantity}
              onChange={(e) => setField("quantity", e.target.value)}
              invalid={invalid}
              className="flex-1"
              data-testid="factory-rfq-quantity"
            />
            <div className="w-24 shrink-0">
              <Select
                options={unitOptions}
                value={draft.qtyUnit}
                onChange={(e) => setField("qtyUnit", e.target.value)}
                aria-label={t("factoryRfq.basic.quantity")}
              />
            </div>
          </div>
        )}
      </FormField>

      <FormField label={t("factoryRfq.basic.targetPrice")}>
        {({ id }) => (
          <div className="flex gap-2">
            <Input
              id={id}
              inputMode="decimal"
              value={draft.targetPrice}
              onChange={(e) => setField("targetPrice", e.target.value)}
              className="flex-1"
              data-testid="factory-rfq-target-price"
            />
            <div className="w-28 shrink-0">
              <Select
                options={currencyOptions}
                value={draft.currency}
                onChange={(e) => setField("currency", e.target.value)}
                aria-label={t("factoryRfq.basic.currency")}
              />
            </div>
          </div>
        )}
      </FormField>

      <FormField label={t("factoryRfq.basic.incoterms")}>
        {({ id }) => (
          <Select
            id={id}
            options={incotermOptions}
            value={draft.incoterms}
            onChange={(e) => setField("incoterms", e.target.value)}
            placeholder={t("factoryRfq.basic.incotermsPlaceholder")}
          />
        )}
      </FormField>

      <FormField label={t("factoryRfq.basic.destinationPort")}>
        {({ id }) => (
          <Input
            id={id}
            value={draft.destinationPort}
            onChange={(e) => setField("destinationPort", e.target.value)}
          />
        )}
      </FormField>

      <FormField label={t("factoryRfq.basic.desiredDeliveryDate")}>
        {({ id }) => (
          <DateInput
            id={id}
            value={draft.desiredDeliveryDate}
            onChange={(e) => setField("desiredDeliveryDate", e.target.value)}
            pickerLabel={t("common.pickDate")}
          />
        )}
      </FormField>

      <StepNav onNext={handleNext} />
    </div>
  );
}
