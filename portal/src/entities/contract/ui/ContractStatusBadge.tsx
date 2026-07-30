import { useTranslation } from "react-i18next";

import { Badge } from "@/shared/ui";
import type { BadgeTone } from "@/shared/ui";

const TONES: Record<string, BadgeTone> = {
  draft: "neutral",
  pending_counterparty: "warning",
  pending_signatures: "info",
  active: "success",
  declined: "danger",
  cancelled: "neutral",
  expired: "neutral",
};

export function ContractStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  return <Badge tone={TONES[status] ?? "neutral"}>{t(`contracts.status.${status}`)}</Badge>;
}
