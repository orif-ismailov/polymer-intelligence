import { Navigate, useParams, useSearchParams } from "react-router-dom";

/**
 * The cabinet twins of the two sheets that are now public.
 *
 * `/cabinet/market/:offerId` and `/cabinet/manufacturers/:companyId` used to be
 * separate pages. Reading them is public now and the signed-in actions mount on
 * the public URL, so the cabinet address has nothing left to render — but it is
 * still baked into notification payloads, Telegram messages and whatever buyers
 * bookmarked, so it redirects rather than 404s.
 *
 * The query string is carried through: `?fromManufacturer=1` is what tells the
 * product sheet to offer factory chat + RFQ instead of the trader inquiry form.
 */
export function RedirectToPublicOffer() {
  const { offerId } = useParams<{ offerId: string }>();
  const [searchParams] = useSearchParams();
  if (!offerId || !Number.isInteger(Number(offerId)))
    return <Navigate to="/market" replace />;
  const query = searchParams.toString();
  return <Navigate to={`/market/${offerId}${query ? `?${query}` : ""}`} replace />;
}

export function RedirectToPublicCompany() {
  const { companyId } = useParams<{ companyId: string }>();
  if (!companyId || !Number.isInteger(Number(companyId)))
    return <Navigate to="/manufacturers" replace />;
  return <Navigate to={`/manufacturers/${companyId}`} replace />;
}
