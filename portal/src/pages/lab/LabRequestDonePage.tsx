import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useLabRequest } from "@/entities/lab-request";
import { LabRequestDone } from "@/features/lab-request";
import { ErrorView, LinkButton, LoadingView } from "@/shared/ui";

/** `/cabinet/lab/requests/:requestId/done` — the success sheet. */
export function LabRequestDonePage() {
  const { t } = useTranslation();
  const params = useParams<{ requestId: string }>();
  const requestId = params.requestId ? Number(params.requestId) : NaN;

  const { activeCompany, isLoading } = useActiveCompany();
  const query = useLabRequest(
    Number.isFinite(requestId) ? requestId : null,
    activeCompany?.id ?? null,
  );

  if (!Number.isFinite(requestId)) return null;
  if (isLoading || query.isLoading) return <LoadingView label={t("common.loading")} />;

  if (query.isError || !query.data) {
    return (
      <ErrorView title={t("errors.notFound")} message={t("errors.notFoundBody")}>
        <LinkButton to="/logistics">{t("labRequest.backToDirectory")}</LinkButton>
      </ErrorView>
    );
  }

  return (
    <div className="mx-auto max-w-3xl pb-10">
      <LabRequestDone request={query.data} />
    </div>
  );
}
