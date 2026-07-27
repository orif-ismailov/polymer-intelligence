import { useTranslation } from "react-i18next";

import { Badge } from "@/shared/ui";
import type { BadgeTone } from "@/shared/ui";

import type { DealStatus } from "../model/types";

/**
 * Colour carries meaning, not order: gold for "waiting on somebody", brand for
 * money and motion, success only for a finished deal, danger for a dispute.
 */
const TONES: Record<DealStatus, BadgeTone> = {
  negotiation: "neutral",
  contract_pending: "gold",
  contract_signed: "info",
  payment_pending: "gold",
  paid_escrow: "brand",
  shipped: "brand",
  delivered: "info",
  completed: "success",
  cancelled: "neutral",
  disputed: "danger",
};

export function DealStatusBadge({ status }: { status: DealStatus }) {
  const { t } = useTranslation();
  return <Badge tone={TONES[status] ?? "neutral"}>{t(`deals.status.${status}`)}</Badge>;
}
