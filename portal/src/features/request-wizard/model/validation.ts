import { PRODUCT_OTHER } from "@/entities/product";

import type { RequestDraft } from "./draftStore";

/** Sheet 1 — a catalog pick or a free-typed name (+ grade for the free path). */
export function isProductChosen(draft: RequestDraft): boolean {
  if (draft.productChoice === PRODUCT_OTHER) {
    return draft.productText.trim() !== "" && draft.gradeText.trim() !== "";
  }
  return draft.productChoice !== "";
}

/** Sheet 2 — positive volume + required destination + delivery band. */
export function isParamsValid(draft: RequestDraft): boolean {
  return (
    Number(draft.volume) > 0 &&
    draft.destinationCountry.trim() !== "" &&
    draft.deliveryBand !== undefined &&
    draft.validityDays > 0
  );
}

/** Sheets 3–4 are optional preferences; nothing blocks «Далее». */
export function canAdvance(step: number, draft: RequestDraft): boolean {
  if (step === 1) return isProductChosen(draft);
  if (step === 2) return isParamsValid(draft);
  return true;
}
