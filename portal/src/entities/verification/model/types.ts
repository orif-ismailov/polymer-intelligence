import type { CaseStatus, CheckStatus } from "@/shared/config";

export interface CaseCheck {
  /** One of the CheckType enum values; typed as string to tolerate unknowns. */
  check_type: string;
  status: CheckStatus;
  detail: Record<string, unknown> | null;
}

export interface CaseOut {
  id: number;
  case_type: string;
  status: CaseStatus;
  submitted_at: string | null;
  checks: CaseCheck[];
}
