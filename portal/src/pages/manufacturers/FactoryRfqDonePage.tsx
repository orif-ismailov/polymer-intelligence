import { useTranslation } from "react-i18next";
import { Navigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { FactoryRfqDone } from "@/features/factory-rfq";
import { LoadingView } from "@/shared/ui";

/** `/cabinet/manufacturers/rfqs/:rfqId/done` — the closing sheet of the factory RFQ flow. */
export function FactoryRfqDonePage() {
  const { t } = useTranslation();
  const params = useParams<{ rfqId: string }>();
  const { activeCompany, isLoading } = useActiveCompany();

  if (isLoading) return <LoadingView label={t("common.loading")} />;
  if (!activeCompany) return <Navigate to="/cabinet/manufacturers" replace />;

  const rfqId = Number(params.rfqId);
  if (!Number.isInteger(rfqId)) return <Navigate to="/cabinet/manufacturers" replace />;

  return (
    <div className="mx-auto max-w-xl pb-10">
      <FactoryRfqDone companyId={activeCompany.id} rfqId={rfqId} />
    </div>
  );
}
