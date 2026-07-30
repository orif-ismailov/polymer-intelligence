import { useTranslation } from "react-i18next";

import { FormField, Input, Textarea } from "@/shared/ui";

import { COUNTED_STEPS, STEP_TERMS } from "../model/constants";
import { useFactoryRfqDraft } from "../model/draftStore";
import { StepNav } from "./StepNav";

interface StepTermsProps {
  onNext: () => void;
  onBack: () => void;
}

/** Sheet 3 — commercial terms. All optional, folded straight into the RFQ row. */
export function StepTerms({ onNext, onBack }: StepTermsProps) {
  const { t } = useTranslation();
  const draft = useFactoryRfqDraft((s) => s.draft);
  const setField = useFactoryRfqDraft((s) => s.setField);

  return (
    <div className="space-y-5" data-testid="factory-rfq-step-3">
      <header>
        <p className="num text-xs text-text-muted">
          {t("factoryRfq.stepOf", { current: STEP_TERMS, total: COUNTED_STEPS })}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-text">{t("factoryRfq.terms.title")}</h2>
      </header>

      <FormField label={t("factoryRfq.terms.paymentMethod")}>
        {({ id }) => (
          <Input
            id={id}
            value={draft.paymentMethod}
            onChange={(e) => setField("paymentMethod", e.target.value)}
            placeholder={t("factoryRfq.terms.paymentMethodPlaceholder")}
          />
        )}
      </FormField>

      <FormField label={t("factoryRfq.terms.offerValidity")}>
        {({ id }) => (
          <Input
            id={id}
            value={draft.offerValidity}
            onChange={(e) => setField("offerValidity", e.target.value)}
            placeholder={t("factoryRfq.terms.offerValidityPlaceholder")}
          />
        )}
      </FormField>

      <FormField label={t("factoryRfq.terms.performanceGuarantee")}>
        {({ id }) => (
          <Input
            id={id}
            value={draft.performanceGuarantee}
            onChange={(e) => setField("performanceGuarantee", e.target.value)}
            placeholder={t("factoryRfq.terms.performanceGuaranteePlaceholder")}
          />
        )}
      </FormField>

      <FormField label={t("factoryRfq.terms.inspectionRequirement")}>
        {({ id }) => (
          <Input
            id={id}
            value={draft.inspectionRequirement}
            onChange={(e) => setField("inspectionRequirement", e.target.value)}
            placeholder={t("factoryRfq.terms.inspectionRequirementPlaceholder")}
          />
        )}
      </FormField>

      <FormField label={t("factoryRfq.terms.additionalRequirements")}>
        {({ id }) => (
          <Textarea
            id={id}
            rows={4}
            value={draft.additionalRequirements}
            onChange={(e) => setField("additionalRequirements", e.target.value)}
            placeholder={t("factoryRfq.terms.additionalRequirementsPlaceholder")}
          />
        )}
      </FormField>

      <StepNav onNext={onNext} onBack={onBack} />
    </div>
  );
}
