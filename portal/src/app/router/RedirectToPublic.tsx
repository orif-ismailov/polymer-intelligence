import { Navigate, useParams, useSearchParams } from "react-router-dom";

/**
 * The cabinet twins of the pages that are now public.
 *
 * `/cabinet/market/:offerId`, `/cabinet/manufacturers/:companyId` and
 * `/cabinet/news[/:signalId]` used to be separate pages. Reading them is public
 * now and the signed-in actions mount on the public URL, so the cabinet address
 * has nothing left to render — but it is still baked into notification payloads,
 * Telegram messages and whatever buyers bookmarked, so it redirects rather than
 * 404s.
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

/**
 * `slug` is a prop rather than a hardcoded `/manufacturers` because each
 * directory collapses onto its public URL on its own schedule, and a second
 * copy of this component per directory is three lines of duplication that would
 * then have to be kept in step.
 */
export function RedirectToPublicCompany({ slug }: { slug: string }) {
  const { companyId } = useParams<{ companyId: string }>();
  if (!companyId || !Number.isInteger(Number(companyId)))
    return <Navigate to={`/${slug}`} replace />;
  return <Navigate to={`/${slug}/${companyId}`} replace />;
}

/**
 * `/cabinet/news/:signalId` → `/news/:signalId`.
 *
 * News was the last page mounted in both tiers off one component. It reads the
 * same either way — there is nothing a session adds to an article — and it now
 * reads from `/public/news/*`, which a signed-out visitor and a crawler can
 * both fetch. The cabinet address is what the `SideNav` pointed at for two
 * releases, so it redirects.
 */
export function RedirectToPublicNewsArticle() {
  const { signalId } = useParams<{ signalId: string }>();
  if (!signalId || !Number.isInteger(Number(signalId)))
    return <Navigate to="/news" replace />;
  return <Navigate to={`/news/${signalId}`} replace />;
}
