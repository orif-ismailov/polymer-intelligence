import { Navigate, useParams } from "react-router-dom";

/**
 * `/cabinet/offers/:offerId` → the first sheet of the edit flow.
 *
 * The bare offer URL is what the list links to and what older links point at, so
 * it stays a valid address; it just resolves to the flow now instead of the
 * single-page form the flow replaced.
 */
export function OfferEditRedirect() {
  const { offerId } = useParams<{ offerId: string }>();
  if (!offerId || !Number.isInteger(Number(offerId)))
    return <Navigate to="/cabinet/offers" replace />;
  return <Navigate to={`/cabinet/offers/${offerId}/edit/1`} replace />;
}
