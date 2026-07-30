import { useEffect, useMemo } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { ChevronLeftIcon, FlowHeader, IconButton, Stepper } from "@/shared/ui";
import type { Step } from "@/shared/ui";

import {
  WIZARD_FIRST_STEP,
  WIZARD_STEP_BANK,
  WIZARD_STEP_COUNT,
  WIZARD_STEP_DETAILS,
  WIZARD_STEP_DOCUMENTS,
  WIZARD_STEP_REVIEW,
  WIZARD_STEP_TYPE,
} from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import {
  areDocumentsValid,
  isAccountTypeValid,
  isBankValid,
  isIdentityValid,
} from "../model/validation";
import { StepAccountType } from "./StepAccountType";
import { StepBank } from "./StepBank";
import { StepDetails } from "./StepDetails";
import { StepDocuments } from "./StepDocuments";
import { StepReview } from "./StepReview";

function clampStep(raw: string | undefined): number {
  const parsed = Number(raw);
  if (!Number.isInteger(parsed)) return WIZARD_FIRST_STEP;
  return Math.min(Math.max(parsed, WIZARD_FIRST_STEP), WIZARD_STEP_COUNT);
}

/**
 * URL-addressable company registration wizard, rendered full-screen: the mockups
 * give registration its own chrome (back chevron, centred title, step rail) with
 * no cabinet nav around it — which is also honest, because a first-time user has
 * no company for that nav to be scoped to yet.
 */
export function CompanyWizard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams<{ step?: string }>();
  const draft = useWizardDraft();

  /**
   * The contiguous run of steps the draft has earned, and therefore both the rail's
   * tick marks and the furthest reachable step.
   *
   * A PREFIX, not an independent per-step test. `isBankValid` returns true for a
   * skipped bank ("skipped is valid"), so testing each step on its own put a tick on
   * «Банк» while the user was still on step 1. A step only counts once everything
   * before it does.
   *
   * Step 5 is deliberately not included — arriving there *is* the submit, so it is
   * never "already done" and must only be reached via «Далее» on step 4. Without
   * this guard `/companies/new/5` was directly addressable with an empty draft and
   * fired a real `POST /portal/companies` carrying a blank STIR.
   */
  const { completedIds, furthestAllowed } = useMemo(() => {
    const satisfied: Array<[number, boolean]> = [
      [WIZARD_STEP_TYPE, isAccountTypeValid(draft.accountType) || draft.companyId != null],
      [WIZARD_STEP_DETAILS, isIdentityValid(draft.identity)],
      [WIZARD_STEP_BANK, isBankValid(draft.bank)],
      [
        WIZARD_STEP_DOCUMENTS,
        areDocumentsValid(draft.documents, draft.bank, draft.identityLocked),
      ],
    ];
    const done: number[] = [];
    for (const [id, ok] of satisfied) {
      if (!ok) break;
      done.push(id);
    }
    const last = done.at(-1);
    return {
      completedIds: done,
      furthestAllowed: last === undefined ? WIZARD_FIRST_STEP : last + 1,
    };
  }, [draft]);

  const requested = clampStep(params.step);
  const step = Math.min(requested, furthestAllowed);

  // Normalize out-of-range / non-numeric / unreachable step params to a canonical URL.
  useEffect(() => {
    if (String(step) !== params.step) {
      void navigate(`/companies/new/${step}`, { replace: true });
    }
  }, [step, params.step, navigate]);

  const goTo = (next: number): void => {
    void navigate(`/companies/new/${next}`);
  };

  const steps: Step[] = [
    { id: WIZARD_STEP_TYPE, label: t("wizard.steps.accountType") },
    { id: WIZARD_STEP_DETAILS, label: t("wizard.steps.details") },
    { id: WIZARD_STEP_BANK, label: t("wizard.steps.bank") },
    { id: WIZARD_STEP_DOCUMENTS, label: t("wizard.steps.documents") },
    { id: WIZARD_STEP_REVIEW, label: t("wizard.steps.review") },
  ];

  return (
    <div className="space-y-6">
      <FlowHeader
        title={t("wizard.title")}
        leading={
          <IconButton
            label={t("common.back")}
            onClick={() => (step > WIZARD_FIRST_STEP ? goTo(step - 1) : void navigate("/companies"))}
          >
            <ChevronLeftIcon size={20} />
          </IconButton>
        }
      />

      <Stepper steps={steps} current={step} completedIds={completedIds} variant="stacked" />

      <div className="pt-2">
        {step === WIZARD_STEP_TYPE ? <StepAccountType onNext={() => goTo(WIZARD_STEP_DETAILS)} /> : null}
        {step === WIZARD_STEP_DETAILS ? (
          <StepDetails onNext={() => goTo(WIZARD_STEP_BANK)} onBack={() => goTo(WIZARD_STEP_TYPE)} />
        ) : null}
        {step === WIZARD_STEP_BANK ? (
          <StepBank onNext={() => goTo(WIZARD_STEP_DOCUMENTS)} onBack={() => goTo(WIZARD_STEP_DETAILS)} />
        ) : null}
        {step === WIZARD_STEP_DOCUMENTS ? (
          <StepDocuments onNext={() => goTo(WIZARD_STEP_REVIEW)} onBack={() => goTo(WIZARD_STEP_BANK)} />
        ) : null}
        {step === WIZARD_STEP_REVIEW ? (
          <StepReview
            onBack={() => goTo(WIZARD_STEP_DOCUMENTS)}
            onComplete={(companyId) => navigate(`/companies/new/done/${companyId}`, { replace: true })}
          />
        ) : null}
      </div>
    </div>
  );
}
