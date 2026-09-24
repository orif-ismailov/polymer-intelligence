import { useTranslation } from "react-i18next";

import type { DealEscrow } from "@/entities/deal";
import { formatDateTime, formatMoney } from "@/shared/lib";
import {
  Alert,
  Badge,
  Card,
  CardBody,
  EmptyState,
  StatChip,
  StatusStepper,
  BankIcon,
} from "@/shared/ui";
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
 *
 * On the DIRECT rail there is no escrow to show: nobody reserves the money and
 * nobody pays it out, so the track is «Ожидает оплаты → Оплата получена», and
 * `released` (the deal closing) reads as paid. The seller's button lives in the
 * action bar with the deal's other moves.
 */
export function DealEscrowPanel({ escrow }: DealEscrowPanelProps) {
  const { t, i18n } = useTranslation();

  if (!escrow) {
    return (
      <EmptyState
          icon={<BankIcon size={28} />}
        title={t("deals.escrow.noneTitle")}
        description={t("deals.escrow.noneBody")}
      />
    );
  }

  const direct = escrow.mode === "direct";
  const refunded = escrow.status === "refunded";
  const flow: DealEscrow["status"][] = refunded
    ? ["pending", "refunded"]
    : direct
      ? ["pending", "funded"]
      : ["pending", "funded", "released"];
  // Direct: `released` only means the deal closed — the money was already paid.
  const shown = direct && escrow.status === "released" ? "funded" : escrow.status;
  const reached = flow.indexOf(shown);
  const label = (status: DealEscrow["status"]) =>
    direct && status !== "refunded"
      ? t(`deals.escrow.direct.${status === "pending" ? "pending" : "paid"}`)
      : t(`deals.escrow.status.${status}`);
  const stampFor: Record<string, string | null> = {
    funded: escrow.funded_at,
    released: escrow.released_at,
    refunded: escrow.refunded_at,
  };

  const steps: StatusStep[] = flow.map((status, index) => ({
    id: status,
    label: label(status),
    hint: stampFor[status] ? formatDateTime(stampFor[status]) : undefined,
    state: index < reached ? "done" : index === reached ? "current" : "pending",
  }));

  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="space-y-4">
          {/* The sheet leads the payment screen with the figure ("Сумма к оплате"),
              so the amount is a metric tile rather than a bold paragraph. */}
          <div className="flex flex-wrap items-start justify-between gap-3">
            <StatChip
              className="min-w-40 flex-1"
              value={formatMoney(escrow.amount, escrow.currency, i18n.language)}
              label={t("deals.escrow.amount")}
              tone="brand"
            />
            <Badge tone={direct && shown === "funded" ? "success" : TONES[escrow.status]}>
              {label(shown)}
            </Badge>
          </div>
          <StatusStepper steps={steps} />
        </CardBody>
      </Card>

      {/* The operator will supply the final wording; the key is what matters. */}
      {direct ? (
        <Alert tone="info" title={t("deals.escrow.direct.title")}>
          {t("deals.escrow.direct.body")}
        </Alert>
      ) : (
        <Alert tone="info" title={t("deals.escrow.bankTitle")}>
          {t("deals.escrow.bankBody")}
        </Alert>
      )}
    </div>
  );
}
