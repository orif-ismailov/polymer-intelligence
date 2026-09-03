import { useTranslation } from "react-i18next";

import { Badge } from "@/shared/ui";
import type { BadgeTone } from "@/shared/ui";

import type { RfqResponse } from "../model/types";

/**
 * A quote's standing, named the same way on both sides of it: the buyer reading
 * their tender's quotes and the supplier reading their own. Only the outcome is
 * coloured — `submitted` is in flight, not good news.
 */
const TONES: Record<RfqResponse["status"], BadgeTone> = {
  submitted: "info",
  accepted: "success",
  not_selected: "neutral",
  withdrawn: "neutral",
};

export function RfqResponseStatusBadge({ status }: { status: RfqResponse["status"] }) {
  const { t } = useTranslation();
  return <Badge tone={TONES[status] ?? "neutral"}>{t(`rfq.status.${status}`)}</Badge>;
}
