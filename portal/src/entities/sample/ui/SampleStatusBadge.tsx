import { useTranslation } from "react-i18next";

import { Badge, type BadgeTone } from "@/shared/ui";

import type { SampleRequestStatus } from "../model/types";

const TONES: Record<SampleRequestStatus, BadgeTone> = {
  requested: "neutral",
  accepted: "info",
  declined: "danger",
  sent: "warning",
  received: "success",
  rejected_by_buyer: "danger",
};

export function SampleStatusBadge({ status }: { status: SampleRequestStatus }) {
  const { t } = useTranslation();
  return <Badge tone={TONES[status]}>{t(`samples.status.${status}`)}</Badge>;
}
