import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { rfqApi, useRfqResponses } from "@/entities/deal";
import type { RfqResponse } from "@/entities/deal";
import { formatDateTime } from "@/shared/lib";
import {
  Alert,
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  Skeleton,
} from "@/shared/ui";
import type { BadgeTone } from "@/shared/ui";

const TONES: Record<RfqResponse["status"], BadgeTone> = {
  submitted: "info",
  accepted: "success",
  not_selected: "neutral",
  withdrawn: "neutral",
};

interface RfqResponseListProps {
  companyId: number;
  requestId: number;
  /** The RFQ owner may accept; a supplier viewing their own quote may not. */
  canAccept: boolean;
}

/**
 * Quotes on an RFQ. The buyer sees them all and accepts one; a supplier sees
 * only their own (the API filters, not this component).
 */
export function RfqResponseList({ companyId, requestId, canAccept }: RfqResponseListProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const query = useRfqResponses(companyId, requestId);
  const [confirming, setConfirming] = useState<RfqResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (query.isLoading) return <Skeleton className="h-24 w-full" />;

  const items = query.data?.items ?? [];
  if (items.length === 0) {
    return <EmptyState title={t("rfq.noResponses")} description={t("rfq.noResponsesBody")} />;
  }

  async function accept(response: RfqResponse): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const deal = await rfqApi.accept(companyId, requestId, response.id);
      void navigate(`/deals/${deal.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
      setBusy(false);
      setConfirming(null);
    }
  }

  return (
    <div className="space-y-3">
      {error ? <Alert tone="danger" title={error} /> : null}

      <ul className="divide-y divide-border rounded-md border border-border">
        {items.map((response) => (
          <li key={response.id} className="flex flex-wrap items-center gap-3 px-3 py-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-sm font-medium text-text">
                  {response.company_name ?? `#${response.company_id}`}
                </span>
                {response.company_verified ? (
                  <Badge variant="verified">{t("market.verified")}</Badge>
                ) : null}
                <Badge tone={TONES[response.status]}>{t(`rfq.status.${response.status}`)}</Badge>
              </div>
              <p className="num mt-1 text-sm text-text-muted">
                <span className="font-semibold text-brand">
                  {response.price} {response.currency}
                </span>
                {" · "}
                {response.qty} {response.qty_unit}
                {response.incoterms ? ` · ${response.incoterms}` : ""}
                {response.lead_time_days != null
                  ? ` · ${t("rfq.leadTimeDays", { count: response.lead_time_days })}`
                  : ""}
              </p>
              {response.comment ? (
                <p className="mt-1 text-sm text-text-muted">{response.comment}</p>
              ) : null}
              <p className="num mt-0.5 text-xs text-text-subtle">
                {formatDateTime(response.created_at)}
              </p>
            </div>

            {response.status === "accepted" && response.deal_id ? (
              <Button size="sm" variant="outline" onClick={() => navigate(`/deals/${response.deal_id}`)}>
                {t("rfq.openDeal")}
              </Button>
            ) : canAccept && response.status === "submitted" ? (
              <Button size="sm" disabled={busy} onClick={() => setConfirming(response)}>
                {t("rfq.accept")}
              </Button>
            ) : null}
          </li>
        ))}
      </ul>

      <ConfirmDialog
        open={confirming !== null}
        title={t("rfq.acceptTitle")}
        // Accepting is irreversible for the other suppliers, so say so plainly.
        description={t("rfq.acceptBody", {
          company: confirming?.company_name ?? "",
          price: `${confirming?.price ?? ""} ${confirming?.currency ?? ""}`,
        })}
        confirmLabel={t("rfq.accept")}
        cancelLabel={t("common.cancel")}
        loading={busy}
        onConfirm={() => {
          if (confirming) void accept(confirming);
        }}
        onClose={() => setConfirming(null)}
      />
    </div>
  );
}
