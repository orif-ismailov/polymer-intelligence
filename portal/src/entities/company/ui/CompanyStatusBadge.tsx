import type { CompanyStatus } from "@/shared/config";
import { COMPANY_STATUS_TONE, toneFor, useEnumLabels } from "@/shared/i18n";
import { Badge } from "@/shared/ui";

interface CompanyStatusBadgeProps {
  status: CompanyStatus;
}

export function CompanyStatusBadge({ status }: CompanyStatusBadgeProps) {
  const label = useEnumLabels();
  return <Badge tone={toneFor(COMPANY_STATUS_TONE, status)}>{label("companyStatus", status)}</Badge>;
}
