import type { CaseStatus, CheckStatus } from "@/shared/config";
import { CASE_STATUS_TONE, CHECK_STATUS_TONE, toneFor, useEnumLabels } from "@/shared/i18n";
import { Badge } from "@/shared/ui";

export function CaseStatusBadge({ status }: { status: CaseStatus }) {
  const label = useEnumLabels();
  return <Badge tone={toneFor(CASE_STATUS_TONE, status)}>{label("caseStatus", status)}</Badge>;
}

export function CheckStatusBadge({ status }: { status: CheckStatus }) {
  const label = useEnumLabels();
  return <Badge tone={toneFor(CHECK_STATUS_TONE, status)}>{label("checkStatus", status)}</Badge>;
}
