import { useId, useState } from "react";

import { useTranslation } from "react-i18next";

import { SALE_MODES } from "@/shared/config";
import {
  Checkbox,
  FormField,
  InfoIcon,
  Input,
  Radio,
  Segmented,
  Select,
  StepPanel,
} from "@/shared/ui";
import type { SelectOption } from "@/shared/ui";

import { COUNTED_STEPS, SAMPLE_BANDS, STEP_TERMS, type SampleBandId } from "../model/constants";
import { useOfferDraft } from "../model/draftStore";
import { isTermsValid } from "../model/validation";
import { StepNav } from "./StepNav";

interface StepTermsProps {
  onNext: () => void;
  onBack: () => void;
}

/** Sheet 6 — «Условия продажи». */
export function StepTerms({ onNext, onBack }: StepTermsProps) {
  const { t } = useTranslation();
  const draft = useOfferDraft((s) => s.draft);
  const setField = useOfferDraft((s) => s.setField);
  const [touched, setTouched] = useState(false);
  const feeName = useId();
  const modeName = useId();

  const valid = isTermsValid(draft);

  const sampleBandOptions: SelectOption[] = SAMPLE_BANDS.map((band) => ({
    value: band.id,
    label: t(`offerWizard.terms.sampleBands.${band.id}`),
  }));

  function handleNext(): void {
    setTouched(true);
    if (valid) onNext();
  }

  return (
    <StepPanel
      step={STEP_TERMS}
      title={t("offerWizard.terms.title")}
      counter={t("offerWizard.stepOf", { current: STEP_TERMS, total: COUNTED_STEPS })}
      data-testid="offer-wizard-step-6"
    >
      <div className="space-y-5">
        <div>
          <p className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-text">
            {t("offers.samplesTitle")}
            <span className="text-text-subtle" title={t("offerWizard.terms.samplesHint")}>
              <InfoIcon size={14} />
            </span>
          </p>
          <Segmented
            ariaLabel={t("offers.samplesTitle")}
            value={draft.samplesAvailable ? "yes" : "no"}
            onChange={(value) => setField("samplesAvailable", value === "yes")}
            options={[
              { value: "yes", label: t("offerWizard.terms.samplesYes") },
              { value: "no", label: t("offerWizard.terms.samplesNo") },
            ]}
            data-testid="offer-wizard-samples"
          />
        </div>

        {draft.samplesAvailable ? (
          <div className="space-y-3">
            <p className="text-sm font-medium text-text">{t("offerWizard.terms.sampleFee")}</p>
            <div className="space-y-2">
              {(["free", "paid"] as const).map((fee) => (
                <Radio
                  key={fee}
                  id={`${feeName}-${fee}`}
                  name={feeName}
                  value={fee}
                  checked={draft.sampleFee === fee}
                  onChange={() => setField("sampleFee", fee)}
                  label={t(`offerWizard.terms.fee.${fee}`)}
                />
              ))}
            </div>

            {draft.sampleFee === "paid" ? (
              <FormField
                label={t("offers.samplePrice")}
                required
                error={touched && !valid ? t("offerWizard.terms.samplePriceRequired") : null}
              >
                {({ id, invalid, describedBy }) => (
                  <Input
                    id={id}
                    inputMode="decimal"
                    value={draft.samplePrice}
                    invalid={invalid}
                    aria-describedby={describedBy}
                    onChange={(e) => setField("samplePrice", e.target.value)}
                  />
                )}
              </FormField>
            ) : null}

            <FormField label={t("offerWizard.terms.sampleDispatch")}>
              {({ id }) => (
                <Select
                  id={id}
                  options={sampleBandOptions}
                  value={draft.sampleBand}
                  onChange={(e) => setField("sampleBand", e.target.value as SampleBandId)}
                />
              )}
            </FormField>
          </div>
        ) : null}

        <div>
          <p className="mb-2 text-sm font-medium text-text">{t("offers.readinessTitle")}</p>
          <div className="space-y-2">
            <Checkbox
              checked={draft.acceptsRfq}
              onChange={(e) => setField("acceptsRfq", e.target.checked)}
              label={t("offerWizard.terms.acceptsRfq")}
            />
            <Checkbox
              checked={draft.acceptsContract}
              onChange={(e) => setField("acceptsContract", e.target.checked)}
              label={t("offerWizard.terms.acceptsContract")}
            />
            <Checkbox
              checked={draft.acceptsEscrow}
              onChange={(e) => setField("acceptsEscrow", e.target.checked)}
              label={t("offerWizard.terms.acceptsEscrow")}
            />
          </div>
        </div>

        <div>
          <p className="mb-2 text-sm font-medium text-text">{t("offers.saleModeLabel")}</p>
          <div className="space-y-2">
            {SALE_MODES.map((mode) => (
              <Radio
                key={mode}
                id={`${modeName}-${mode}`}
                name={modeName}
                value={mode}
                checked={draft.saleMode === mode}
                onChange={() => setField("saleMode", mode)}
                label={t(`offers.saleMode.${mode}`)}
              />
            ))}
          </div>
        </div>
      </div>

      <StepNav onNext={handleNext} onBack={onBack} />
    </StepPanel>
  );
}
