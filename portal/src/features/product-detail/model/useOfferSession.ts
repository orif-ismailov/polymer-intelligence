import { selectIsAuthenticated, useAuthStore } from "@/entities/account";
import { useActiveCompany } from "@/entities/company";
import { useMarketOffer } from "@/entities/market";
import type { MarketOfferDetail } from "@/entities/market";
import type { CompanySummary } from "@/entities/company";

export interface OfferSession {
  /** The authenticated payload: `is_own`, `is_favorite`, `accepts_*`, `my_inquiries`. */
  offer: MarketOfferDetail;
  companyId: number | null;
  activeCompany: CompanySummary | null;
}

/**
 * The signed-in half of `/market/:offerId`, or `null`.
 *
 * `/market/:offerId` is one URL for everyone: a crawler and an anonymous
 * visitor read it, and a signed-in visitor also acts on it. Acting needs fields
 * the public payload deliberately withholds — `is_favorite`, `is_own`,
 * `accepts_rfq`, `accepts_contract`, `my_inquiries` — so this fetches the
 * cabinet payload alongside the public one.
 *
 * Both queries are gated on `selectIsAuthenticated`, which is `token !== null`.
 * That is false during SSR and at first paint, and only flips once the boot-time
 * refresh resolves. So the server issues no authenticated request, the cached
 * HTML is identical for every visitor, and the actions arrive as a state change
 * after hydration rather than as a hydration mismatch — the same contract
 * `PublicTopNav` already lives under.
 *
 * Returns `null` until all of that has settled, so a caller can treat it as
 * "there is nobody to act as (yet)".
 */
export function useOfferSession(offerId: number | null): OfferSession | null {
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const { activeCompany } = useActiveCompany(isAuthenticated);
  const companyId = activeCompany?.id ?? null;
  const offerQuery = useMarketOffer(isAuthenticated ? offerId : null, companyId);

  if (!isAuthenticated || !offerQuery.data) return null;
  return { offer: offerQuery.data, companyId, activeCompany };
}
