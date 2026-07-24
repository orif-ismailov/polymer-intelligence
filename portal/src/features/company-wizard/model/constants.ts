import type { DocumentKind } from "@/shared/config";

export const DEFAULT_JURISDICTION = "UZ";

export const WIZARD_STEP_COUNT = 5;
export const WIZARD_FIRST_STEP = 1;
export const WIZARD_CONFIRM_STEP = 5;

/** Document kinds surfaced as dropzones in the wizard (step 4). */
export const WIZARD_DOCUMENT_KINDS: readonly DocumentKind[] = [
  "registration_certificate",
  "bank_letter",
  "director_id",
  "license",
];

/** Always-required documents regardless of other inputs. */
export const ALWAYS_REQUIRED_DOCS: readonly DocumentKind[] = ["registration_certificate"];

/** Deep-link map: which wizard step a failing verification check points back to. */
export const CHECK_TO_STEP: Record<string, number> = {
  tax_id_format: 1,
  bank_requisites: 3,
  documents_complete: 4,
  manual_kyb: 5,
};
