import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { usePublicCompany } from "@/entities/public";
import { LogisticsRequestForm } from "@/features/logistics-request";
import { ErrorView, LinkButton, LoadingView, PageHeader } from "@/shared/ui";

/**
 * `/cabinet/logistics/:companyId/request` — «Заявка логистической компании».
 *
 * A cabinet route rather than a slot on the public profile, for three reasons:
 * the sheet has its own chrome and header; `RequireAuth` + `RequireCompany`
 * already are the gate this flow needs, with the right onboarding redirect; and
 * the public profile's HTML is shared-cached (`s-maxage=60`), so anything
 * mounted there is something that must be proven never to reach the anonymous
 * render.
 *
 * The carrier's name comes from the PUBLIC endpoint — it is the same company the
 * visitor was just reading, already in the query cache from the profile they
 * came from, so the header fills in without a second round trip.
 */
export function LogisticsRequestPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams<{ companyId: string }>();
  const logisticsId = params.companyId ? Number(params.companyId) : NaN;

  const { activeCompany, isLoading } = useActiveCompany();
  const carrier = usePublicCompany("logistics", Number.isFinite(logisticsId) ? logisticsId : null);

  if (!Number.isFinite(logisticsId)) return null;
  if (isLoading) return <LoadingView label={t("common.loading")} />;

  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")}>
        <LinkButton to="/cabinet/companies/new/1">{t("companies.create")}</LinkButton>
      </ErrorView>
    );
  }

  const carrierName =
    carrier.data?.short_name ?? carrier.data?.legal_name ?? t("logisticsRequest.title");

  return (
    <div className="mx-auto max-w-3xl pb-10">
      <PageHeader
        backTo={`/logistics/${logisticsId}`}
        backLabel={t("companyProfile.title")}
        title={t("logisticsRequest.title")}
        subtitle={carrierName}
      />
      <div className="mt-5">
        <LogisticsRequestForm
          logisticsId={logisticsId}
          companyId={activeCompany.id}
          onSent={(requestId) =>
            navigate(`/cabinet/logistics/requests/${requestId}/done`, { replace: true })
          }
        />
      </div>
    </div>
  );
}
