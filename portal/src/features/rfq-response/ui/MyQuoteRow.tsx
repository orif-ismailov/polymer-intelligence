import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import { RfqResponseStatusBadge, TenderRow, useWithdrawRfqResponse } from "@/entities/deal";
import type { MyRfqResponse } from "@/entities/deal";
import { formatDateTime } from "@/shared/lib";
import { Alert, Badge, Button, ConfirmDialog } from "@/shared/ui";

interface MyQuoteRowProps {
  quote: MyRfqResponse;
  companyId: number;
  /** Arrived from the «предложение не выбрано» bell — scroll to it. */
  highlighted?: boolean;
}

/**
 * One quote this company filed, as a row of the tender it answers.
 *
 * The tender's facts stay in their columns so the two tabs read alike; the
 * status column carries the supplier's own price, their terms under it, and
 * where the buyer has got to with it; under the product, their comment and when
 * they filed it. Withdrawal is
 * offered exactly while the API allows it (`submitted`) — anything later is the
 * buyer's move, not ours.
 */
export function MyQuoteRow({ quote, companyId, highlighted }: MyQuoteRowProps) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rowRef = useRef<HTMLLIElement>(null);
  const withdraw = useWithdrawRfqResponse(companyId);

  useEffect(() => {
    if (highlighted) rowRef.current?.scrollIntoView({ block: "center" });
  }, [highlighted]);

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

  const terms = [
    `${quote.qty} ${quote.qty_unit}`,
    quote.incoterms,
    quote.lead_time_days != null ? t("rfq.leadTimeDays", { count: quote.lead_time_days }) : null,
  ].filter(Boolean);

  return (
    <TenderRow
      request={quote.request}
      rowRef={rowRef}
      highlighted={highlighted}
      statusLabel={t("rfq.columns.yourQuote")}
      status={
        <div className="space-y-1.5">
          <div>
            <p className="num font-semibold text-brand">
              {quote.price} {quote.currency}
            </p>
            <p className="num text-xs text-text-muted">{terms.join(" · ")}</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <RfqResponseStatusBadge status={quote.status} />
            {/* A closed tender explains a quote that will never move again. */}
            {!quote.request_open ? (
              <Badge tone="neutral">{t("rfq.mine.tenderClosed")}</Badge>
            ) : null}
          </div>
        </div>
      }
      detail={
        <div className="mt-1 space-y-0.5 text-sm">
          {quote.comment ? <p className="line-clamp-2 text-text-muted">{quote.comment}</p> : null}
          <p className="num text-xs text-text-subtle">{formatDateTime(quote.created_at)}</p>
        </div>
      }
      action={
        quote.status === "submitted" ? (
          <>
            <Button
              size="sm"
              variant="outline"
              fullWidth
              disabled={withdraw.isPending}
              onClick={() => setConfirming(true)}
            >
              {t("rfq.withdraw")}
            </Button>
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
          </>
        ) : null
      }
      panel={error ? <Alert tone="danger" title={error} /> : null}
    />
  );
}
