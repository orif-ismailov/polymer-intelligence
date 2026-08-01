import { useTranslation } from "react-i18next";
import { Navigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { PublishDone } from "@/features/request-wizard";
import { LoadingView } from "@/shared/ui";

/** `/cabinet/requests/new/done/:requestId` — the closing sheet of the request flow. */
export function RequestPublishedPage() {
  const { t } = useTranslation();
  const params = useParams<{ requestId: string }>();
  const { activeCompany, isLoading } = useActiveCompany();

  if (isLoading) return <LoadingView label={t("common.loading")} />;
  if (!activeCompany) return <Navigate to="/cabinet/requests" replace />;

  const requestId = Number(params.requestId);
  if (!Number.isInteger(requestId)) return <Navigate to="/cabinet/requests" replace />;

  return (
    <div className="mx-auto max-w-xl pb-10">
      <PublishDone companyId={activeCompany.id} requestId={requestId} />
    </div>
  );
}
