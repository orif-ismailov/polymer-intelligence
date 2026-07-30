import { useEffect, useRef } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { RequestWizard, clampStep, useRequestDraft } from "@/features/request-wizard";
import { ErrorView, LinkButton, LoadingView } from "@/shared/ui";

/**
 * Host for the new-purchase-request flow at `/requests/new/:step`.
 *
 * The step lives in the URL (same pattern as the add-product and registration
 * wizards): a reload and the browser back button land where they say they will,
 * and the draft in the store survives the hop.
 */
export function RequestCreatePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams<{ step?: string }>();
  const step = clampStep(params.step);

  const { activeCompany, isLoading } = useActiveCompany();
  const begin = useRequestDraft((s) => s.begin);
  const reset = useRequestDraft((s) => s.reset);

  const base = "/requests/new";

  useEffect(() => {
    if (String(step) !== params.step) void navigate(`${base}/${step}`, { replace: true });
  }, [step, params.step, navigate]);

  const seeded = useRef(false);
  useEffect(() => {
    if (!activeCompany || seeded.current) return;
    seeded.current = true;
    const name =
      activeCompany.short_name ?? activeCompany.legal_name ?? activeCompany.tax_id;
    begin(name);
  }, [activeCompany, begin]);

  useEffect(() => () => reset(), [reset]);

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
      <RequestWizard
        companyId={activeCompany.id}
        step={step}
        onStepChange={(next) => navigate(`${base}/${next}`)}
        onExit={() => navigate("/requests")}
        onPublished={(id) => navigate(`/requests/new/done/${id}`, { replace: true })}
      />
    </div>
  );
}
