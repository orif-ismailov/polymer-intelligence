import { PRODUCT_OTHER } from "@/entities/product";

import {
  OTHER_OPTION,
  REQUIRED_DOCUMENT_KINDS,
  STEP_AI_CHECK,
  STEP_AVAILABILITY,
  STEP_BASICS,
  STEP_DOCUMENTS,
  STEP_EXTRA,
  STEP_LAB,
  STEP_PREVIEW,
  STEP_TERMS,
  type OfferDocumentKind,
} from "./constants";
import { warehouseValue, type OfferDraft, type StagedFile } from "./draftStore";

/** What the «Далее» button on a sheet needs before it lights up. */
export interface StepInputs {
  draft: OfferDraft;
  /** Documents staged on this visit, plus what the server already holds. */
  documentKinds: ReadonlySet<OfferDocumentKind>;
  /** True once the AI sheet has finished its pass. */
  aiChecked: boolean;
}

function isPositive(value: string): boolean {
  const n = Number(value);
  return value.trim() !== "" && Number.isFinite(n) && n > 0;
}

/** «Название товара» is answered by a catalog pick OR a typed name, never neither. */
export function isProductNamed(draft: OfferDraft): boolean {
  if (draft.productChoice === PRODUCT_OTHER) return draft.productText.trim() !== "";
  return draft.productChoice !== "";
}

export function isBasicsValid(draft: OfferDraft): boolean {
  return isProductNamed(draft);
}

/**
 * «В наличии» needs a quantity, a price and somewhere to ship from — that is
 * what "in stock" claims. «Под заказ» needs none of the three: it has no stock
 * and its price is "по запросу", so the dispatch band (always set) is the whole
 * promise.
 */
export function isAvailabilityValid(draft: OfferDraft): boolean {
  if (draft.warehouseChoice === OTHER_OPTION && warehouseValue(draft) === "") return false;
  if (draft.availability === "on_order") return true;
  return isPositive(draft.qty) && isPositive(draft.price);
}

export function missingDocumentKinds(
  present: ReadonlySet<OfferDocumentKind>,
): OfferDocumentKind[] {
  return REQUIRED_DOCUMENT_KINDS.filter((kind) => !present.has(kind));
}

/**
 * The passport sheet: claiming to have one and attaching nothing is the only
 * failure. «Нет паспорта» is a complete answer — the sheet then offers to
 * arrange the analysis, which is not a precondition for publishing.
 */
export function isLabValid(draft: OfferDraft, passport: StagedFile | null, onServer: boolean): boolean {
  if (!draft.hasPassport) return true;
  return passport !== null || onServer;
}

export function isTermsValid(draft: OfferDraft): boolean {
  if (!draft.samplesAvailable) return true;
  if (draft.sampleFee === "free") return true;
  const price = Number(draft.samplePrice);
  return draft.samplePrice.trim() !== "" && Number.isFinite(price) && price >= 0;
}

/** Whether a given sheet is complete enough to leave. */
export function isStepValid(step: number, inputs: StepInputs, passport: StagedFile | null, passportOnServer: boolean): boolean {
  switch (step) {
    case STEP_BASICS:
      return isBasicsValid(inputs.draft);
    case STEP_AI_CHECK:
      return inputs.aiChecked;
    case STEP_AVAILABILITY:
      return isAvailabilityValid(inputs.draft);
    case STEP_DOCUMENTS:
      return missingDocumentKinds(inputs.documentKinds).length === 0;
    case STEP_LAB:
      return isLabValid(inputs.draft, passport, passportOnServer);
    case STEP_TERMS:
      return isTermsValid(inputs.draft);
    case STEP_EXTRA:
    case STEP_PREVIEW:
      return true;
    default:
      return false;
  }
}
