import { useTranslation } from "react-i18next";
import { Navigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { PublishDone } from "@/features/offer-wizard";
import { LoadingView } from "@/shared/ui";

/** `/offers/new/done/:offerId` — the closing sheet of the add-product flow. */
export function OfferPublishedPage() {
  const { t } = useTranslation();
  const params = useParams<{ offerId: string }>();
  const { activeCompany, isLoading } = useActiveCompany();

  if (isLoading) return <LoadingView label={t("common.loading")} />;
  if (!activeCompany) return <Navigate to="/offers" replace />;

  const offerId = Number(params.offerId);
  if (!Number.isInteger(offerId)) return <Navigate to="/offers" replace />;

  return (
    <div className="mx-auto max-w-xl">
      <PublishDone companyId={activeCompany.id} offerId={offerId} />
    </div>
  );
}
