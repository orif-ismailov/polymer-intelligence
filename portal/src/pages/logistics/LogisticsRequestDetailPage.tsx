import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useLogisticsRequest } from "@/entities/logistics-request";
import { LogisticsRequestSummary } from "@/features/logistics-request";
import { ErrorView, LinkButton, LoadingView, PageHeader } from "@/shared/ui";

/**
 * `/cabinet/logistics/requests/:requestId` — one request, from either side.
 *
 * The perspective is derived rather than passed in the URL: whichever company is
 * active decides whether this row is something you sent or something you were
 * sent, and the backend has already refused the request if it is neither.
 */
export function LogisticsRequestDetailPage() {
  const { t } = useTranslation();
  const params = useParams<{ requestId: string }>();
  const requestId = params.requestId ? Number(params.requestId) : NaN;

  const { activeCompany, isLoading } = useActiveCompany();
  const query = useLogisticsRequest(
    Number.isFinite(requestId) ? requestId : null,
    activeCompany?.id ?? null,
  );

  if (!Number.isFinite(requestId)) return null;
  if (isLoading || query.isLoading) return <LoadingView label={t("common.loading")} />;

  if (query.isError || !query.data) {
    return (
      <ErrorView title={t("errors.notFound")} message={t("errors.notFoundBody")}>
        <LinkButton to="/cabinet/logistics/requests">
          {t("logisticsRequest.myRequests")}
        </LinkButton>
      </ErrorView>
    );
  }

  const request = query.data;
  const perspective =
    activeCompany && request.logistics_company_id === activeCompany.id ? "carrier" : "buyer";

  return (
    <div className="space-y-5">
      <PageHeader
        backTo="/cabinet/logistics/requests"
        backLabel={t("logisticsRequest.myRequests")}
        title={request.cargo_name}
        subtitle={request.number}
      />
      <LogisticsRequestSummary request={request} perspective={perspective} />
    </div>
  );
}
