import { useTranslation } from "react-i18next";

import { ChipInput, FormField, StepPanel, Textarea } from "@/shared/ui";

import { COUNTED_STEPS, STEP_EXTRA } from "../model/constants";
import { useOfferDraft } from "../model/draftStore";
import { StepNav } from "./StepNav";

interface StepExtraProps {
  onNext: () => void;
  onBack: () => void;
}

/** Sheet 7 — «Дополнительная информация». */
export function StepExtra({ onNext, onBack }: StepExtraProps) {
  const { t } = useTranslation();
  const draft = useOfferDraft((s) => s.draft);
  const setField = useOfferDraft((s) => s.setField);

  return (
    <StepPanel
      step={STEP_EXTRA}
      title={t("offerWizard.extra.title")}
      counter={t("offerWizard.stepOf", { current: STEP_EXTRA, total: COUNTED_STEPS })}
      data-testid="offer-wizard-step-7"
    >
      <div className="space-y-5">
        <FormField label={t("offerWizard.extra.description")}>
          {({ id }) => (
            <Textarea
              id={id}
              rows={6}
              value={draft.description}
              placeholder={t("offerWizard.extra.descriptionPlaceholder")}
              onChange={(e) => setField("description", e.target.value)}
              data-testid="offer-wizard-description"
            />
          )}
        </FormField>

        <FormField label={t("offerWizard.extra.keyProperties")}>
          {({ id }) => (
            <ChipInput
              id={id}
              values={draft.keyProperties}
              onChange={(values) => setField("keyProperties", values)}
              placeholder={t("offerWizard.extra.keyPropertiesPlaceholder")}
              addLabel={t("common.add")}
              removeLabel={t("common.remove")}
              data-testid="offer-wizard-properties"
            />
          )}
        </FormField>

        <FormField label={t("offerWizard.extra.applications")}>
          {({ id }) => (
            <ChipInput
              id={id}
              values={draft.applications}
              onChange={(values) => setField("applications", values)}
              placeholder={t("offerWizard.extra.applicationsPlaceholder")}
              addLabel={t("common.add")}
              removeLabel={t("common.remove")}
              data-testid="offer-wizard-applications"
            />
          )}
        </FormField>
      </div>

      <StepNav onNext={onNext} onBack={onBack} />
    </StepPanel>
  );
}
