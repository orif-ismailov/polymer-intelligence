import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useOffer, type CompanyOffer } from "@/entities/offer";
import { LabPassportBlock } from "@/features/lab-passport";
import { OfferForm, OfferPhotos } from "@/features/offer-form";
import { OffersLocked } from "@/pages/offers";
import {
  Card,
  CardBody,
  ErrorView,
  LinkButton,
  LoadingView,
  PageHeader,
} from "@/shared/ui";

export function OfferEditPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams<{ offerId?: string }>();
  const isCreate = params.offerId === undefined;
  const offerId = isCreate ? null : Number(params.offerId);

  const { activeCompany, isLoading: companyLoading } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const offerQuery = useOffer(companyId, offerId);
  // Photo changes return the updated offer; hold it locally so the gallery and the
  // moderation-status banner reflect the change without a refetch round-trip.
  const [photoOffer, setPhotoOffer] = useState<CompanyOffer | null>(null);

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

  const offer = isCreate ? null : photoOffer ?? offerQuery.data ?? null;

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      {/* The card repeated the page title verbatim; one of them had to go. */}
      <PageHeader
        backTo="/offers"
        backLabel={t("offers.title")}
        title={isCreate ? t("offers.create") : t("offers.edit")}
        subtitle={t("offers.subtitle", { company: companyName })}
      />

      <Card>
        <CardBody>
          <OfferForm
            companyId={activeCompany.id}
            offer={offer}
            onSaved={(saved) =>
              // Photos attach to an offer id, so a brand-new offer lands on its own
              // edit screen where the photo section is available, rather than
              // bouncing straight back to the list.
              navigate(isCreate ? `/offers/${saved.id}` : "/offers", { replace: isCreate })
            }
            onCancel={() => navigate("/offers")}
            onNotVerified={() =>
              navigate(`/companies/${activeCompany.id}/verification`, { replace: true })
            }
          />
        </CardBody>
      </Card>

      {offer ? (
        <OfferPhotos
          companyId={activeCompany.id}
          offer={offer}
          onChanged={setPhotoOffer}
        />
      ) : null}

      {/* Rendered on the create screen too, where it explains why it is inert:
          a passport needs an offer to attach to. Hiding it would leave a seller
          wondering whether the platform does laboratory analysis at all. */}
      <LabPassportBlock
        companyId={activeCompany.id}
        offer={offer}
        onUploaded={setPhotoOffer}
      />
    </div>
  );
}
