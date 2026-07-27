import type { CompanyStatus } from "@/shared/config";
import { COMPANY_STATUS_TONE, toneFor, useEnumLabels } from "@/shared/i18n";
import { Badge } from "@/shared/ui";

interface CompanyStatusBadgeProps {
  status: CompanyStatus;
}

export function CompanyStatusBadge({ status }: CompanyStatusBadgeProps) {
  const label = useEnumLabels();
  // `verified` is the mockups' signature badge — green with a tick.
  if (status === "verified") {
    return <Badge variant="verified">{label("companyStatus", status)}</Badge>;
  }
  return <Badge tone={toneFor(COMPANY_STATUS_TONE, status)}>{label("companyStatus", status)}</Badge>;
}
