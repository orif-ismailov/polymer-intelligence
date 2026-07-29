import { useEffect } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { Card, CardBody, PageHeader, Stepper } from "@/shared/ui";
import type { Step } from "@/shared/ui";

import { WIZARD_CONFIRM_STEP, WIZARD_FIRST_STEP, WIZARD_STEP_COUNT } from "../model/constants";
import { StepBank } from "./StepBank";
import { StepConfirm } from "./StepConfirm";
import { StepDocuments } from "./StepDocuments";
import { StepIdentity } from "./StepIdentity";
import { StepRoles } from "./StepRoles";

function clampStep(raw: string | undefined): number {
  const parsed = Number(raw);
  if (!Number.isInteger(parsed)) return WIZARD_FIRST_STEP;
  return Math.min(Math.max(parsed, WIZARD_FIRST_STEP), WIZARD_STEP_COUNT);
}

/**
 * URL-addressable company registration wizard. The `:step` route param drives
 * which step renders; navigation guards the range and the draft store carries
 * state across steps.
 */
export function CompanyWizard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams<{ step?: string }>();
  const step = clampStep(params.step);

  // Normalize out-of-range / non-numeric step params to a canonical URL.
  useEffect(() => {
    if (String(step) !== params.step) {
      void navigate(`/companies/new/${step}`, { replace: true });
    }
  }, [step, params.step, navigate]);

  const goTo = (next: number): void => {
    void navigate(`/companies/new/${next}`);
  };

  const steps: Step[] = [
    { id: 1, label: t("wizard.steps.identity") },
    { id: 2, label: t("wizard.steps.roles") },
    { id: 3, label: t("wizard.steps.bank") },
    { id: 4, label: t("wizard.steps.documents") },
    { id: 5, label: t("wizard.steps.confirm") },
  ];

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <PageHeader
        backTo="/companies"
        backLabel={t("nav.companies")}
        title={t("wizard.title")}
        subtitle={t("wizard.step", { current: step, total: WIZARD_STEP_COUNT })}
      />

      <Stepper steps={steps} current={step} />

      <Card>
        <CardBody>
          {step === 1 ? <StepIdentity onNext={() => goTo(2)} /> : null}
          {step === 2 ? <StepRoles onNext={() => goTo(3)} onBack={() => goTo(1)} /> : null}
          {step === 3 ? <StepBank onNext={() => goTo(4)} onBack={() => goTo(2)} /> : null}
          {step === 4 ? <StepDocuments onNext={() => goTo(5)} onBack={() => goTo(3)} /> : null}
          {step === WIZARD_CONFIRM_STEP ? (
            <StepConfirm
              onBack={() => goTo(4)}
              onEditStep={goTo}
              onComplete={(companyId) => navigate(`/companies/${companyId}/verification`)}
            />
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}
