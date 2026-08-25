import { useTranslation } from "react-i18next";

import { Badge, type BadgeTone } from "@/shared/ui";

import type { SampleRequestStatus } from "../model/types";

const TONES: Record<SampleRequestStatus, BadgeTone> = {
  // Something is OWED by the person looking at it — the buyer still has to sign
  // the letter, and until they do the seller cannot even see the request.
  pending_letter: "warning",
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
