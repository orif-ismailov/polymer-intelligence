import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useOffer } from "@/entities/offer";
import { OfferForm } from "@/features/offer-form";
import { OffersLocked } from "@/pages/offers";
import { Card, CardBody, CardHeader, CardTitle, ErrorView, LinkButton, LoadingView } from "@/shared/ui";

export function OfferEditPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams<{ offerId?: string }>();
  const isCreate = params.offerId === undefined;
  const offerId = isCreate ? null : Number(params.offerId);

  const { activeCompany, isLoading: companyLoading } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const offerQuery = useOffer(companyId, offerId);

  if (companyLoading) return <LoadingView label={t("common.loading")} />;

  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")}>
        <LinkButton to="/companies/new/1">{t("companies.create")}</LinkButton>
      </ErrorView>
    );
  }

  const companyName = activeCompany.legal_name ?? activeCompany.short_name ?? activeCompany.tax_id;

  // Guard the create flow against the verification requirement up front.
  if (activeCompany.status !== "verified") {
    return <OffersLocked companyId={activeCompany.id} companyName={companyName} />;
  }

  if (!isCreate && offerQuery.isLoading) return <LoadingView label={t("common.loading")} />;
  if (!isCreate && offerQuery.isError) {
    return (
      <ErrorView
        title={t("errors.loadFailed")}
        retryLabel={t("common.retry")}
        onRetry={() => void offerQuery.refetch()}
      />
    );
  }

  const offer = isCreate ? null : offerQuery.data ?? null;

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-text">
          {isCreate ? t("offers.create") : t("offers.edit")}
        </h1>
        <p className="mt-1 text-sm text-text-muted">{t("offers.subtitle", { company: companyName })}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{isCreate ? t("offers.create") : t("offers.edit")}</CardTitle>
        </CardHeader>
        <CardBody>
          <OfferForm
            companyId={activeCompany.id}
            offer={offer}
            onSaved={() => navigate("/offers")}
            onCancel={() => navigate("/offers")}
            onNotVerified={() =>
              navigate(`/companies/${activeCompany.id}/verification`, { replace: true })
            }
          />
        </CardBody>
      </Card>
    </div>
  );
}
