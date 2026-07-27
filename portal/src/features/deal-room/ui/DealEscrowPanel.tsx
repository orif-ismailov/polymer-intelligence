import { useTranslation } from "react-i18next";

import type { DealEscrow } from "@/entities/deal";
import { formatDateTime, formatMoney } from "@/shared/lib";
import { Alert, Badge, Card, CardBody, EmptyState, StatusStepper } from "@/shared/ui";
import type { BadgeTone, StatusStep } from "@/shared/ui";

interface DealEscrowPanelProps {
  escrow: DealEscrow | null;
}

const TONES: Record<DealEscrow["status"], BadgeTone> = {
  pending: "warning",
  funded: "info",
  released: "success",
  refunded: "neutral",
};

/**
 * The payment side of the Trade Room, read-only for both parties.
 *
 * There is nothing to click here on purpose: money is moved by the bank and
 * confirmed by an operator, so the room shows where it is and when it got there.
 * A refunded escrow shows two steps, not four — a refund is where that payment
 * ended, and drawing "released" behind it as if still pending would be a lie.
 */
export function DealEscrowPanel({ escrow }: DealEscrowPanelProps) {
  const { t, i18n } = useTranslation();

  if (!escrow) {
    return (
      <EmptyState
        title={t("deals.escrow.noneTitle")}
        description={t("deals.escrow.noneBody")}
      />
    );
  }

  const refunded = escrow.status === "refunded";
  const flow: DealEscrow["status"][] = refunded
    ? ["pending", "refunded"]
    : ["pending", "funded", "released"];
  const reached = flow.indexOf(escrow.status);
  const stampFor: Record<string, string | null> = {
    funded: escrow.funded_at,
    released: escrow.released_at,
    refunded: escrow.refunded_at,
  };

  const steps: StatusStep[] = flow.map((status, index) => ({
    id: status,
    label: t(`deals.escrow.status.${status}`),
    hint: stampFor[status] ? formatDateTime(stampFor[status]) : undefined,
    state: index < reached ? "done" : index === reached ? "current" : "pending",
  }));

  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="space-y-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="num text-xl font-semibold text-text">
              {formatMoney(escrow.amount, escrow.currency, i18n.language)}
            </p>
            <Badge tone={TONES[escrow.status]}>
              {t(`deals.escrow.status.${escrow.status}`)}
            </Badge>
          </div>
          <StatusStepper steps={steps} />
        </CardBody>
      </Card>

      {/* The operator will supply the final wording; the key is what matters. */}
      <Alert tone="info" title={t("deals.escrow.bankTitle")}>
        {t("deals.escrow.bankBody")}
      </Alert>
    </div>
  );
}
