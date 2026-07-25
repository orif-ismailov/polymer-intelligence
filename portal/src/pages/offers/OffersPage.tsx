import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { useActiveCompany } from "@/entities/company";
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
  Skeleton,
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
          <OfferStatusBadge status={offer.status} />
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-text-muted">{t("offers.availability")}</dt>
            <dd className="font-medium text-text">{label("availability", offer.availability)}</dd>
          </div>
          <div>
            <dt className="text-text-muted">{t("offers.qtyAvailable")}</dt>
            <dd className="font-medium text-text">{formatQty(offer.qty_available, offer.qty_unit, lang)}</dd>
          </div>
          <div>
            <dt className="text-text-muted">{t("offers.price")}</dt>
            <dd className="font-medium text-text">{formatMoney(offer.price, offer.currency, lang)}</dd>
          </div>
          <div>
            <dt className="text-text-muted">{t("offers.incoterms")}</dt>
            <dd className="font-medium text-text">{offer.incoterms}</dd>
          </div>
          <div>
            <dt className="text-text-muted">{t("offers.createdAt")}</dt>
            <dd className="font-medium text-text">{formatDate(offer.created_at, lang)}</dd>
          </div>
        </dl>

        {offer.moderation_note ? (
          <p className="rounded-md bg-surface-2 px-3 py-2 text-sm text-text-muted">
            <span className="font-medium text-text">{t("offers.moderationNote")}:</span>{" "}
            {offer.moderation_note}
          </p>
        ) : null}

        <div className="flex justify-end gap-3 border-t border-border pt-3">
          {offer.status === "approved" ? (
            <LinkButton size="sm" variant="secondary" to={`/contracts/new?offerId=${offer.id}`}>
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
        title={t("home.noActiveCompany")}
        description={t("home.noActiveCompanyBody")}
        action={<LinkButton to="/companies/new/1">{t("companies.create")}</LinkButton>}
      />
    );
  }

  const companyName = activeCompany.legal_name ?? activeCompany.short_name ?? activeCompany.tax_id;

  if (activeCompany.status !== "verified") {
    return <OffersLocked companyId={activeCompany.id} companyName={companyName} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text">{t("offers.title")}</h1>
          <p className="mt-1 text-sm text-text-muted">
            {t("offers.subtitle", { company: companyName })}
          </p>
        </div>
        <LinkButton to="/offers/new">{t("offers.create")}</LinkButton>
      </div>

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
              onEdit={(id) => navigate(`/offers/${id}`)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title={t("offers.empty")}
          description={t("offers.emptyBody")}
          action={<LinkButton to="/offers/new">{t("offers.create")}</LinkButton>}
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
