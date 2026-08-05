import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { useActiveCompany } from "@/entities/company";
import { ComplianceRequirements, RegulationBadge } from "@/entities/compliance";
import { OfferStatusBadge, useArchiveOffer, useOffers } from "@/entities/offer";
import type { CompanyOffer } from "@/entities/offer";
import { coerceLang, useEnumLabels } from "@/shared/i18n";
import { formatDate, formatMoney, formatQty } from "@/shared/lib";
import {
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  EmptyState,
  ErrorView,
  LinkButton,
  LoadingView,
  PageHeader,
  Skeleton,
  SpecItem,
  SpecList,
  BoxIcon,
  RegistryIcon,
} from "@/shared/ui";

import { OffersLocked } from "./OffersLocked";

function OfferCard({
  offer,
  lang,
  onArchive,
  onEdit,
}: {
  offer: CompanyOffer;
  lang: string;
  onArchive: (id: number) => void;
  onEdit: (id: number) => void;
}) {
  const { t } = useTranslation();
  const label = useEnumLabels();
  const canArchive = offer.status !== "archived";

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-base font-semibold text-text">
              {offer.product_text ?? t("offers.product")}
            </p>
            <p className="mt-0.5 text-sm text-text-muted">
              {[offer.grade_text, offer.polymer_type].filter(Boolean).join(" · ") || "—"}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            {offer.substance ? (
              <RegulationBadge level={offer.substance.regulation_level} />
            ) : null}
            <OfferStatusBadge status={offer.status} />
          </div>
        </div>

        <SpecList className="sm:grid-cols-3">
          <SpecItem
            label={t("offers.availability")}
            value={label("availability", offer.availability)}
          />
          <SpecItem
            label={t("offers.qtyAvailable")}
            value={formatQty(offer.qty_available, offer.qty_unit, lang)}
            numeric
          />
          <SpecItem
            label={t("offers.price")}
            value={formatMoney(offer.price, offer.currency, lang)}
            numeric
          />
          <SpecItem label={t("offers.incoterms")} value={offer.incoterms} />
          <SpecItem
            label={t("offers.createdAt")}
            value={formatDate(offer.created_at, lang)}
            numeric
          />
        </SpecList>

        {/* Why a held offer is a draft (P5): the gate saved it rather than
            losing the form, and this is the list of what it is waiting for. */}
        {offer.compliance_missing && offer.compliance_missing.length > 0 ? (
          <ComplianceRequirements
            level={offer.compliance_level ?? "free"}
            missing={offer.compliance_missing}
            enforced={offer.status === "draft"}
            substanceName={offer.substance?.name_ru ?? null}
          />
        ) : null}

        {offer.moderation_note ? (
          <p className="rounded-md bg-surface-2 px-3 py-2 text-sm text-text-muted">
            <span className="font-medium text-text">{t("offers.moderationNote")}:</span>{" "}
            {offer.moderation_note}
          </p>
        ) : null}

        <div className="flex justify-end gap-3 border-t border-border pt-3">
          {offer.status === "approved" ? (
            <LinkButton size="sm" variant="secondary" to={`/cabinet/contracts/new?offerId=${offer.id}`}>
              {t("contracts.create")}
            </LinkButton>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => onEdit(offer.id)}>
            {t("common.edit")}
          </Button>
          {canArchive ? (
            <Button size="sm" variant="outline" onClick={() => onArchive(offer.id)}>
              {t("common.archive")}
            </Button>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}

export function OffersPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const lang = coerceLang(useAuthStore((s) => s.account?.language));
  const { activeCompany, isLoading: companiesLoading } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const offersQuery = useOffers(companyId);
  const archive = useArchiveOffer(companyId ?? -1);
  const [archiveId, setArchiveId] = useState<number | null>(null);

  if (companiesLoading) return <LoadingView label={t("common.loading")} />;

  if (!activeCompany) {
    return (
      <EmptyState
          icon={<RegistryIcon size={28} />}
        title={t("home.noActiveCompany")}
        description={t("home.noActiveCompanyBody")}
        action={<LinkButton to="/cabinet/companies/new/1">{t("companies.create")}</LinkButton>}
      />
    );
  }

  const companyName = activeCompany.legal_name ?? activeCompany.short_name ?? activeCompany.tax_id;

  if (activeCompany.status !== "verified") {
    return <OffersLocked companyId={activeCompany.id} companyName={companyName} />;
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title={t("offers.title")}
        subtitle={t("offers.subtitle", { company: companyName })}
        actions={<LinkButton to="/cabinet/offers/new">{t("offers.create")}</LinkButton>}
      />

      {offersQuery.isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : offersQuery.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void offersQuery.refetch()}
        />
      ) : offersQuery.data && offersQuery.data.length > 0 ? (
        <div className="space-y-4">
          {offersQuery.data.map((offer) => (
            <OfferCard
              key={offer.id}
              offer={offer}
              lang={lang}
              onArchive={setArchiveId}
              onEdit={(id) => navigate(`/cabinet/offers/${id}`)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<BoxIcon size={28} />}
          title={t("offers.empty")}
          description={t("offers.emptyBody")}
          action={<LinkButton to="/cabinet/offers/new">{t("offers.create")}</LinkButton>}
        />
      )}

      <ConfirmDialog
        open={archiveId !== null}
        title={t("common.archive")}
        description={t("offers.archiveConfirm")}
        confirmLabel={t("common.archive")}
        cancelLabel={t("common.cancel")}
        loading={archive.isPending}
        onClose={() => setArchiveId(null)}
        onConfirm={() => {
          if (archiveId !== null) archive.mutate(archiveId, { onSuccess: () => setArchiveId(null) });
        }}
      />
    </div>
  );
}
