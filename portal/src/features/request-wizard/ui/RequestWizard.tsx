import { useTranslation } from "react-i18next";

import { ChevronLeftIcon, IconButton, Stepper } from "@/shared/ui";
import type { Step } from "@/shared/ui";

import {
  FIRST_STEP,
  STEP_COMM,
  STEP_EXTRA,
  STEP_PARAMS,
  STEP_PREVIEW,
  STEP_PRODUCT,
} from "../model/constants";
import { useSubmitRequest } from "../model/useSubmitRequest";
import { PublishDone } from "./PublishDone";
import { StepComm } from "./StepComm";
import { StepExtra } from "./StepExtra";
import { StepParams } from "./StepParams";
import { StepPreview } from "./StepPreview";
import { StepProduct } from "./StepProduct";

interface RequestWizardProps {
  companyId: number;
  step: number;
  onStepChange: (step: number) => void;
  onExit: () => void;
  onPublished: (requestId: number) => void;
}

/**
 * The new-purchase-request flow (`docs/new-design/request_page.jpeg`).
 *
 * Chrome first — back chevron, title, five-step rail — then whichever sheet the
 * URL names. Sheets own their own validation and their own «Далее»; this
 * component only decides which one is on screen and what publishing means.
 */
export function RequestWizard({
  companyId,
  step,
  onStepChange,
  onExit,
  onPublished,
}: RequestWizardProps) {
  const { t } = useTranslation();
  const save = useSubmitRequest(companyId);

  const steps: Step[] = [
    { id: 1, label: t("requestWizard.steps.product") },
    { id: 2, label: t("requestWizard.steps.params") },
    { id: 3, label: t("requestWizard.steps.extra") },
    { id: 4, label: t("requestWizard.steps.comm") },
    { id: 5, label: t("requestWizard.steps.preview") },
  ];

  async function publish(): Promise<void> {
    const saved = await save.submit();
    if (saved) onPublished(saved.id);
  }

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <div className="flex items-start gap-2">
          <IconButton
            label={t("common.back")}
            onClick={() => (step > FIRST_STEP ? onStepChange(step - 1) : onExit())}
          >
            <ChevronLeftIcon size={20} />
          </IconButton>
          <div className="min-w-0 flex-1">
            <h1 className="text-lg font-semibold leading-tight text-text">
              {t("requestWizard.title")}
            </h1>
            <p className="mt-1 text-sm text-text-muted">{t("requestWizard.subtitle")}</p>
          </div>
        </div>
      </header>

      <Stepper steps={steps} current={step} variant="stacked" />

      <div className="pt-1">
        {step === STEP_PRODUCT ? (
          <StepProduct onNext={() => onStepChange(STEP_PARAMS)} />
        ) : null}
        {step === STEP_PARAMS ? (
          <StepParams
            onNext={() => onStepChange(STEP_EXTRA)}
            onBack={() => onStepChange(STEP_PRODUCT)}
          />
        ) : null}
        {step === STEP_EXTRA ? (
          <StepExtra
            onNext={() => onStepChange(STEP_COMM)}
            onBack={() => onStepChange(STEP_PARAMS)}
          />
        ) : null}
        {step === STEP_COMM ? (
          <StepComm
            onNext={() => onStepChange(STEP_PREVIEW)}
            onBack={() => onStepChange(STEP_EXTRA)}
          />
        ) : null}
        {step === STEP_PREVIEW ? (
          <StepPreview
            error={save.error}
            isPending={save.isPending}
            onPublish={() => void publish()}
            onEdit={() => onStepChange(STEP_PRODUCT)}
          />
        ) : null}
      </div>
    </div>
  );
}

export { PublishDone };
