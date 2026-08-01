import { useParams } from "react-router-dom";

import { CompanyProfileView } from "@/features/company-profile";

/**
 * `/cabinet/manufacturers/:companyId` — manufacturer profile.
 *
 * Reuses the same public-profile sheet as `/cabinet/sellers/:id` and `/cabinet/companies/:id`
 * so the chrome stays identical; `mode="manufacturer"` swaps the buyer footer
 * to the chat + factory-RFQ actions (`docs/new-design/manufacturer_flow.jpeg`).
 */
export function ManufacturerDetailPage() {
  const { companyId: rawId } = useParams<{ companyId: string }>();
  const companyId = rawId ? Number(rawId) : NaN;

  if (!Number.isFinite(companyId)) return null;

  return <CompanyProfileView companyId={companyId} backTo="/cabinet/manufacturers" mode="manufacturer" />;
}
