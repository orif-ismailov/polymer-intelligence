import { useParams, useSearchParams } from "react-router-dom";

import { CompanyProfileView } from "@/features/company-profile";

/**
 * Public seller company profile — `docs/new-design/company_profile.jpeg`.
 *
 * Opened from a product-detail seller card when `seller_company_id` is set.
 * `?fromOffer=` carries the offer the buyer came from so «Написать» can return
 * to that offer's inquiry form.
 *
 * UI lives in `CompanyProfileView` so `/cabinet/companies/:id` can reuse the same sheet.
 */
export function SellerProfilePage() {
  const { companyId: rawId } = useParams<{ companyId: string }>();
  const companyId = rawId ? Number(rawId) : NaN;
  const [search] = useSearchParams();
  const fromOffer = search.get("fromOffer");
  const fromOfferId = fromOffer && /^\d+$/.test(fromOffer) ? Number(fromOffer) : null;

  if (!Number.isFinite(companyId)) return null;

  return (
    <CompanyProfileView companyId={companyId} fromOfferId={fromOfferId} />
  );
}
