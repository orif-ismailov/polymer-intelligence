import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { OfferStatusBadge, useOffer } from "@/entities/offer";
import {
  Button,
  Card,
  CardBody,
  CheckIcon,
  Confetti,
  CopyIcon,
  ErrorView,
  LoadingView,
  SuccessMark,
} from "@/shared/ui";

interface PublishDoneProps {
  companyId: number;
  offerId: number;
}

/**
 * «Публикация успешна» — the closing sheet.
 *
 * The status line is the offer's ACTUAL state, not the mockup's literal
 * "опубликован": a new offer lands in `pending_moderation` and a held one stays
 * a `draft` until its requirement is met. Telling a seller their goods are live
 * when a moderator has not seen them yet is the one thing this screen must not
 * do — so the celebration is real, and the badge under it is honest.
 */
export function PublishDone({ companyId, offerId }: PublishDoneProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const query = useOffer(companyId, offerId);
  const [copied, setCopied] = useState(false);

  if (query.isLoading) return <LoadingView label={t("common.loading")} />;
  if (query.isError || !query.data) {
    return (
      <ErrorView
        title={t("errors.loadFailed")}
        retryLabel={t("common.retry")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const offer = query.data;
  const publicId = `#IMX-${String(offer.id).padStart(6, "0")}`;
  const live = offer.status === "approved";

  function copy(): void {
    void navigator.clipboard?.writeText(publicId).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="relative" data-testid="offer-wizard-done">
      <Confetti className="-top-6 h-64" />

      <div className="relative flex flex-col items-center pt-6 text-center">
        <SuccessMark size="lg" />
        <h1 className="mt-6 text-3xl font-semibold leading-tight text-text">
          {t("offerWizard.done.title")}
        </h1>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-text-muted">
          {live ? t("offerWizard.done.bodyLive") : t("offerWizard.done.bodyModeration")}
        </p>
        <div className="mt-4">
          <OfferStatusBadge status={offer.status} />
        </div>
      </div>

      <Card className="mt-8">
        <CardBody>
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm text-text-muted">{t("offerWizard.done.idLabel")}</p>
              <p className="num mt-1 text-xl font-semibold text-text" data-testid="offer-wizard-public-id">
                {publicId}
              </p>
            </div>
            <button
              type="button"
              onClick={copy}
              aria-label={t("offerWizard.done.copyId")}
              className="rounded-md border border-border p-2.5 text-text-muted transition-colors hover:border-brand-line hover:bg-brand-soft hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {copied ? <CheckIcon size={18} /> : <CopyIcon size={18} />}
            </button>
          </div>
        </CardBody>
      </Card>

      <div className="mt-6 space-y-3">
        <Button
          fullWidth
          size="lg"
          onClick={() => void navigate("/cabinet/offers")}
          data-testid="offer-wizard-done-list"
        >
          {t("offerWizard.done.toOffers")}
        </Button>
        <Button
          fullWidth
          size="lg"
          variant="outline"
          onClick={() => void navigate("/cabinet/offers/new/1")}
          data-testid="offer-wizard-done-another"
        >
          {t("offerWizard.done.createAnother")}
        </Button>
      </div>
    </div>
  );
}
