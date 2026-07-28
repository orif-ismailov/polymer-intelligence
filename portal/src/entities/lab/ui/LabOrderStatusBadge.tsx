import { useTranslation } from "react-i18next";

import { Badge, type BadgeTone } from "@/shared/ui";

import type { LabOrderStatus } from "../model/types";

const TONES: Record<LabOrderStatus, BadgeTone> = {
  submitted: "neutral",
  accepted: "info",
  sample_awaited: "warning",
  in_analysis: "info",
  done: "success",
  rejected: "danger",
};

export function LabOrderStatusBadge({ status }: { status: LabOrderStatus }) {
  const { t } = useTranslation();
  return <Badge tone={TONES[status]}>{t(`lab.status.${status}`)}</Badge>;
}
