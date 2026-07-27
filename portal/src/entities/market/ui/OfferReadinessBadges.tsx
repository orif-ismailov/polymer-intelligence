import { useTranslation } from "react-i18next";

import { Badge } from "@/shared/ui";

import type { MarketOffer } from "../model/types";

interface OfferReadinessBadgesProps {
  offer: Pick<MarketOffer, "accepts_rfq" | "accepts_contract" | "accepts_escrow">;
  className?: string;
}

/**
 * What this seller is ready to do: answer an RFQ, sign a contract, use escrow.
 *
 * Only what is switched ON is drawn. A row of greyed-out "no" badges would read
 * as a list of refusals; absence says the same thing without the noise.
 */
export function OfferReadinessBadges({ offer, className }: OfferReadinessBadgesProps) {
  const { t } = useTranslation();
  const flags: [boolean, string][] = [
    [offer.accepts_rfq, "market.readiness.rfq"],
    [offer.accepts_contract, "market.readiness.contract"],
    [offer.accepts_escrow, "market.readiness.escrow"],
  ];
  const on = flags.filter(([enabled]) => enabled);
  if (on.length === 0) return null;

  return (
    <div className={className}>
      <div className="flex flex-wrap gap-1.5">
        {on.map(([, key]) => (
          <Badge key={key} tone="info">
            {t(key)}
          </Badge>
        ))}
      </div>
    </div>
  );
}
