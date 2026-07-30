import { useTranslation } from "react-i18next";

import type { CompanyOffer } from "@/entities/offer";
import { Alert, ChevronLeftIcon, IconButton, Stepper } from "@/shared/ui";
import type { Step } from "@/shared/ui";

import {
  FIRST_STEP,
  STEP_AI_CHECK,
  STEP_AVAILABILITY,
  STEP_BASICS,
  STEP_DOCUMENTS,
  STEP_EXTRA,
  STEP_LAB,
  STEP_PREVIEW,
  STEP_TERMS,
} from "../model/constants";
import { useSubmitOffer } from "../model/useSubmitOffer";
import { AssuranceStrip, TrustChips } from "./WizardChrome";
import { StepAiCheck } from "./StepAiCheck";
import { StepAvailability } from "./StepAvailability";
import { StepBasics } from "./StepBasics";
import { StepDocuments } from "./StepDocuments";
import { StepExtra } from "./StepExtra";
import { StepLab } from "./StepLab";
import { StepPreview } from "./StepPreview";
import { StepTerms } from "./StepTerms";

interface OfferWizardProps {
  companyId: number;
  /** True when the flow reopened an existing offer. */
  isEdit: boolean;
  step: number;
  onStepChange: (step: number) => void;
  /** Leaving the flow from sheet 1's «Назад». */
  onExit: () => void;
  onPublished: (offer: CompanyOffer) => void;
  onNotVerified: () => void;
}

/**
 * The add-product flow (`docs/new-design/product_creation.jpeg`).
 *
 * Chrome first — the masthead with its trust chips, the seven-step rail, the
 * reassurance strip along the foot — then whichever sheet the URL names. The
 * sheets own their own validation and their own «Далее»; this component only
 * decides which one is on screen and what publishing means.
 */
export function OfferWizard({
  companyId,
  isEdit,
  step,
  onStepChange,
  onExit,
  onPublished,
  onNotVerified,
}: OfferWizardProps) {
  const { t } = useTranslation();
  const save = useSubmitOffer(companyId);

  /*
   * The rail is numbered 1–7 (the mockup's seven discs). The flow has eight
   * sheets: Extra is «Шаг 7 из 7» on the collage, and Preview is the same rail
   * stop painted as «Публикация». URL ids stay 1…8 (preview = 8) so deep links
   * do not collide; only the painted disc is remapped here. Mapping Extra onto
   * disc 6 used to leave the Extra sheet saying «7» while the rail sat on «6».
   */
  const steps: Step[] = [
    { id: 1, label: t("offerWizard.steps.basics") },
    { id: 2, label: t("offerWizard.steps.ai") },
    { id: 3, label: t("offerWizard.steps.availability") },
    { id: 4, label: t("offerWizard.steps.documents") },
    { id: 5, label: t("offerWizard.steps.lab") },
    { id: 6, label: t("offerWizard.steps.terms") },
    { id: 7, label: t("offerWizard.steps.publish") },
  ];

  const railStep =
    step === STEP_TERMS
      ? 6
      : step === STEP_EXTRA || step === STEP_PREVIEW
        ? 7
        : step;

  async function publish(): Promise<void> {
    const saved = await save.submit();
    if (saved) onPublished(saved);
    else if (save.notVerified) onNotVerified();
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
              {isEdit ? t("offerWizard.editTitle") : t("offerWizard.title")}
            </h1>
            <p className="mt-1 text-sm text-text-muted">{t("offerWizard.subtitle")}</p>
          </div>
        </div>
        <TrustChips />
      </header>

      <Stepper steps={steps} current={railStep} variant="stacked" />

      {save.notVerified ? (
        <Alert tone="danger" title={t("offers.lockedTitle")}>
          {t("offers.notVerifiedError")}
        </Alert>
      ) : null}

      <div className="pt-1">
        {step === STEP_BASICS ? (
          <StepBasics
            companyId={companyId}
            onNext={() => onStepChange(STEP_AI_CHECK)}
          />
        ) : null}
        {step === STEP_AI_CHECK ? (
          <StepAiCheck
            companyId={companyId}
            onNext={() => onStepChange(STEP_AVAILABILITY)}
            onBack={() => onStepChange(STEP_BASICS)}
          />
        ) : null}
        {step === STEP_AVAILABILITY ? (
          <StepAvailability
            onNext={() => onStepChange(STEP_DOCUMENTS)}
            onBack={() => onStepChange(STEP_AI_CHECK)}
          />
        ) : null}
        {step === STEP_DOCUMENTS ? (
          <StepDocuments
            onNext={() => onStepChange(STEP_LAB)}
            onBack={() => onStepChange(STEP_AVAILABILITY)}
          />
        ) : null}
        {step === STEP_LAB ? (
          <StepLab
            companyId={companyId}
            onNext={() => onStepChange(STEP_TERMS)}
            onBack={() => onStepChange(STEP_DOCUMENTS)}
          />
        ) : null}
        {step === STEP_TERMS ? (
          <StepTerms
            onNext={() => onStepChange(STEP_EXTRA)}
            onBack={() => onStepChange(STEP_LAB)}
          />
        ) : null}
        {step === STEP_EXTRA ? (
          <StepExtra
            onNext={() => onStepChange(STEP_PREVIEW)}
            onBack={() => onStepChange(STEP_TERMS)}
          />
        ) : null}
        {step === STEP_PREVIEW ? (
          <StepPreview
            companyId={companyId}
            isEdit={isEdit}
            progress={save.progress}
            error={save.notVerified ? null : save.error}
            onPublish={() => void publish()}
            onBack={() => onStepChange(STEP_EXTRA)}
          />
        ) : null}
      </div>

      <AssuranceStrip />
    </div>
  );
}
