import { useTranslation } from "react-i18next";

import { CheckStatusBadge } from "@/entities/verification";
import type { CaseCheck } from "@/entities/verification";
import { useEnumLabels } from "@/shared/i18n";

/** Extract a human-readable explanation from a check's freeform detail object. */
function explain(detail: Record<string, unknown> | null): string | null {
  if (!detail) return null;
  const candidates = ["message", "reason", "detail", "note", "explanation"];
  for (const key of candidates) {
    const value = detail[key];
    if (typeof value === "string" && value.trim() !== "") return value;
  }
  return null;
}

interface CheckRowProps {
  check: CaseCheck;
}

export function CheckRow({ check }: CheckRowProps) {
  const { t } = useTranslation();
  const label = useEnumLabels();
  const explanation = explain(check.detail);

  return (
    <li className="flex items-start justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-text">{label("verification.checkTypes", check.check_type)}</p>
        <p className="mt-0.5 text-xs text-text-muted">
          {explanation ?? t("verification.checkDetail.empty")}
        </p>
      </div>
      <CheckStatusBadge status={check.status} />
    </li>
  );
}
