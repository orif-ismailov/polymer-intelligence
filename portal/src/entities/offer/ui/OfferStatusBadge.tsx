import type { OfferStatus } from "@/shared/config";
import { OFFER_STATUS_TONE, toneFor, useEnumLabels } from "@/shared/i18n";
import { Badge } from "@/shared/ui";

export function OfferStatusBadge({ status }: { status: OfferStatus }) {
  const label = useEnumLabels();
  return <Badge tone={toneFor(OFFER_STATUS_TONE, status)}>{label("offerStatus", status)}</Badge>;
}
