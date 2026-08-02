import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { LogisticsRequestForm } from "@/features/logistics-request";
import { ErrorView, LinkButton, LoadingView, PageHeader } from "@/shared/ui";

/**
 * `/cabinet/logistics/requests/new` — «Заявка логистической компании».
 *
 * A cabinet route rather than a slot on a carrier's public profile: the sheet
 * has its own chrome, `RequireAuth` + `RequireCompany` already are the gate this
 * flow needs, and the public profile's HTML is shared-cached (`s-maxage=60`), so
 * anything mounted there must be proven never to reach the anonymous render.
 *
 * No carrier in the path any more — the request is broadcast to all of them.
 */
export function LogisticsRequestPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeCompany, isLoading } = useActiveCompany();

  if (isLoading) return <LoadingView label={t("common.loading")} />;

  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")}>
        <LinkButton to="/cabinet/companies/new/1">{t("companies.create")}</LinkButton>
      </ErrorView>
    );
  }

  return (
    <div className="mx-auto max-w-3xl pb-10">
      <PageHeader
        backTo="/cabinet/logistics/requests"
        backLabel={t("logisticsRequest.myRequests")}
        title={t("logisticsRequest.title")}
        subtitle={t("logisticsRequest.broadcastHint")}
      />
      <div className="mt-5">
        <LogisticsRequestForm
          companyId={activeCompany.id}
          onSent={(requestId) =>
            navigate(`/cabinet/logistics/requests/${requestId}/done`, { replace: true })
          }
        />
      </div>
    </div>
  );
}
