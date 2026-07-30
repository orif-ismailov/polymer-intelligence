import { useTranslation } from "react-i18next";

import { ChevronLeftIcon, IconButton, Stepper } from "@/shared/ui";
import type { Step } from "@/shared/ui";

import { STEP_BASIC, STEP_CONTACT, STEP_DOCUMENTS, STEP_TERMS } from "../model/constants";
import { useSubmitFactoryRfq } from "../model/useSubmitFactoryRfq";
import { StepBasic } from "./StepBasic";
import { StepContact } from "./StepContact";
import { StepDocuments } from "./StepDocuments";
import { StepTerms } from "./StepTerms";

interface FactoryRfqWizardProps {
  companyId: number;
  manufacturerId: number;
  offerId: number;
  step: number;
  onStepChange: (step: number) => void;
  onExit: () => void;
  onSubmitted: (rfqId: number) => void;
}

/**
 * Extended factory RFQ (`docs/new-design/manufacturer_flow.jpeg`).
 *
 * Chrome first — back chevron, title, four-step rail — then whichever sheet the
 * caller names. Sheets own their own validation; this component only decides
 * which one is on screen and what submitting means.
 */
export function FactoryRfqWizard({
  companyId,
  manufacturerId,
  offerId,
  step,
  onStepChange,
  onExit,
  onSubmitted,
}: FactoryRfqWizardProps) {
  const { t } = useTranslation();
  const save = useSubmitFactoryRfq(manufacturerId);

  const steps: Step[] = [
    { id: 1, label: t("factoryRfq.steps.basic") },
    { id: 2, label: t("factoryRfq.steps.documents") },
    { id: 3, label: t("factoryRfq.steps.terms") },
    { id: 4, label: t("factoryRfq.steps.contact") },
  ];

  async function submit(): Promise<void> {
    const rfq = await save.submit(companyId, offerId);
    if (rfq) onSubmitted(rfq.id);
  }

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <div className="flex items-start gap-2">
          <IconButton
            label={t("common.back")}
            onClick={() => (step > STEP_BASIC ? onStepChange(step - 1) : onExit())}
          >
            <ChevronLeftIcon size={20} />
          </IconButton>
          <div className="min-w-0 flex-1">
            <h1 className="text-lg font-semibold leading-tight text-text">
              {t("factoryRfq.title")}
            </h1>
            <p className="mt-1 text-sm text-text-muted">{t("factoryRfq.subtitle")}</p>
          </div>
        </div>
      </header>

      <Stepper steps={steps} current={step} variant="stacked" />

      <div className="pt-1">
        {step === STEP_BASIC ? <StepBasic onNext={() => onStepChange(STEP_DOCUMENTS)} /> : null}
        {step === STEP_DOCUMENTS ? (
          <StepDocuments
            onNext={() => onStepChange(STEP_TERMS)}
            onBack={() => onStepChange(STEP_BASIC)}
          />
        ) : null}
        {step === STEP_TERMS ? (
          <StepTerms
            onNext={() => onStepChange(STEP_CONTACT)}
            onBack={() => onStepChange(STEP_DOCUMENTS)}
          />
        ) : null}
        {step === STEP_CONTACT ? (
          <StepContact
            error={save.error}
            isPending={save.isPending}
            onSubmit={() => void submit()}
            onBack={() => onStepChange(STEP_TERMS)}
          />
        ) : null}
      </div>
    </div>
  );
}
