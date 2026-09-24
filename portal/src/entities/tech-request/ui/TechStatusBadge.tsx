import { useTranslation } from "react-i18next";

import { Badge, type BadgeTone } from "@/shared/ui";

import type { TechOfferStatus, TechRequestStatus } from "../model/types";

const REQUEST_TONE: Record<TechRequestStatus, BadgeTone> = {
  open: "brand",
  assigned: "info",
  completed: "success",
  cancelled: "neutral",
};

const OFFER_TONE: Record<TechOfferStatus, BadgeTone> = {
  submitted: "warning",
  accepted: "success",
  declined: "neutral",
  withdrawn: "neutral",
};

export function TechRequestStatusBadge({ status }: { status: TechRequestStatus }) {
  const { t } = useTranslation();
  return <Badge tone={REQUEST_TONE[status]}>{t(`techRequest.status.${status}`)}</Badge>;
}

export function TechOfferStatusBadge({ status }: { status: TechOfferStatus }) {
  const { t } = useTranslation();
  return <Badge tone={OFFER_TONE[status]}>{t(`techOffer.status.${status}`)}</Badge>;
}
