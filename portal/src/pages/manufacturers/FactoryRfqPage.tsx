import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { FactoryRfqWizard, STEP_BASIC, useFactoryRfqDraft } from "@/features/factory-rfq";
import { ErrorView, LinkButton, LoadingView } from "@/shared/ui";

/**
 * `/manufacturers/:companyId/rfq/:offerId` — the 4-step factory RFQ flow.
 *
 * The step lives in local state rather than the URL: the route contract for
 * this flow is a single addressable path, unlike the request/offer wizards.
 */
export function FactoryRfqPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams<{ companyId: string; offerId: string }>();
  const manufacturerId = params.companyId ? Number(params.companyId) : NaN;
  const offerId = params.offerId ? Number(params.offerId) : NaN;
  const { activeCompany, isLoading } = useActiveCompany();

  const [step, setStep] = useState(STEP_BASIC);
  const begin = useFactoryRfqDraft((s) => s.begin);
  const reset = useFactoryRfqDraft((s) => s.reset);

  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current) return;
    seeded.current = true;
    begin();
  }, [begin]);

  useEffect(() => () => reset(), [reset]);

  if (!Number.isFinite(manufacturerId) || !Number.isFinite(offerId)) return null;
  if (isLoading) return <LoadingView label={t("common.loading")} />;

  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")}>
        <LinkButton to="/companies/new/1">{t("companies.create")}</LinkButton>
      </ErrorView>
    );
  }

  return (
    <div className="mx-auto max-w-3xl pb-10">
      <FactoryRfqWizard
        companyId={activeCompany.id}
        manufacturerId={manufacturerId}
        offerId={offerId}
        step={step}
        onStepChange={setStep}
        onExit={() => navigate(`/manufacturers/${manufacturerId}`)}
        onSubmitted={(rfqId) => navigate(`/manufacturers/rfqs/${rfqId}/done`, { replace: true })}
      />
    </div>
  );
}
