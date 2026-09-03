import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import { RfqResponseStatusBadge, useWithdrawRfqResponse } from "@/entities/deal";
import type { MyRfqResponse } from "@/entities/deal";
import { formatDate, formatDateTime } from "@/shared/lib";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  SpecItem,
  SpecList,
} from "@/shared/ui";

interface MyQuoteCardProps {
  quote: MyRfqResponse;
  companyId: number;
  /** Arrived from the «предложение не выбрано» bell — open and scroll to it. */
  highlighted?: boolean;
}

/**
 * One quote this company filed, and the tender it answers.
 *
 * The tender is on top because that is what the supplier recognises the row by;
 * their own price sits under it, which is the only number on the card that is
 * theirs. Withdrawal is offered exactly while the API allows it (`submitted`) —
 * anything later is the buyer's move, not ours.
 */
export function MyQuoteCard({ quote, companyId, highlighted }: MyQuoteCardProps) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const withdraw = useWithdrawRfqResponse(companyId);

  useEffect(() => {
    if (highlighted) cardRef.current?.scrollIntoView({ block: "center" });
  }, [highlighted]);

  const request = quote.request;
  const destination = [request.port_or_city, request.destination_country]
    .filter(Boolean)
    .join(", ");

  async function confirmWithdraw(): Promise<void> {
    setError(null);
    try {
      await withdraw.mutateAsync({ requestId: quote.request_id, responseId: quote.id });
      setConfirming(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
      setConfirming(false);
    }
  }

  return (
    <div ref={cardRef}>
      <Card className={highlighted ? "border-brand" : undefined}>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-semibold text-text">{request.product ?? "—"}</p>
              {request.grade ? (
                <p className="truncate text-xs text-text-muted">{request.grade}</p>
              ) : null}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {/* A closed tender explains a quote that will never move again. */}
              {!quote.request_open ? (
                <Badge tone="neutral">{t("rfq.mine.tenderClosed")}</Badge>
              ) : null}
              <RfqResponseStatusBadge status={quote.status} />
            </div>
          </div>

          <SpecList>
            <SpecItem
              label={t("rfq.volume")}
              value={`${request.volume} ${request.volume_unit}`}
              numeric
            />
            <SpecItem label={t("rfq.incoterms")} value={request.incoterms} />
            <SpecItem label={t("rfq.destination")} value={destination || "—"} />
            <SpecItem
              label={t("rfq.desiredDate")}
              value={request.desired_date ? formatDate(request.desired_date) : "—"}
              numeric
            />
          </SpecList>

          <div className="rounded-md border border-border bg-surface-2 px-3 py-2">
            <p className="text-xs text-text-subtle">{t("rfq.mine.yourPrice")}</p>
            <p className="num mt-0.5 text-sm text-text">
              <span className="font-semibold text-brand">
                {quote.price} {quote.currency}
              </span>
              {" · "}
              {quote.qty} {quote.qty_unit}
              {quote.incoterms ? ` · ${quote.incoterms}` : ""}
              {quote.lead_time_days != null
                ? ` · ${t("rfq.leadTimeDays", { count: quote.lead_time_days })}`
                : ""}
            </p>
            {quote.comment ? (
              <p className="mt-1 text-sm text-text-muted">{quote.comment}</p>
            ) : null}
            <p className="num mt-0.5 text-xs text-text-subtle">
              {formatDateTime(quote.created_at)}
            </p>
          </div>

          {error ? <Alert tone="danger" title={error} /> : null}

          {quote.status === "submitted" ? (
            <Button
              size="sm"
              variant="outline"
              disabled={withdraw.isPending}
              onClick={() => setConfirming(true)}
            >
              {t("rfq.withdraw")}
            </Button>
          ) : null}
        </CardBody>
      </Card>

      <ConfirmDialog
        open={confirming}
        title={t("rfq.withdrawTitle")}
        description={t("rfq.withdrawBody")}
        confirmLabel={t("rfq.withdraw")}
        cancelLabel={t("common.cancel")}
        loading={withdraw.isPending}
        onConfirm={() => void confirmWithdraw()}
        onClose={() => setConfirming(false)}
      />
    </div>
  );
}
