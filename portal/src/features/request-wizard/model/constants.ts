/**
 * The new-purchase-request flow (`docs/new-design/request_page.jpeg`).
 *
 * Five collecting/review sheets on the rail, then the published celebration —
 * which is NOT step 6 of the rail: the mockup's rail ends at «Проверьте и
 * опубликуйте», and the done sheet is what happens after Publish.
 */

export const STEP_PRODUCT = 1;
export const STEP_PARAMS = 2;
export const STEP_EXTRA = 3;
export const STEP_COMM = 4;
export const STEP_PREVIEW = 5;

export const FIRST_STEP = STEP_PRODUCT;
export const LAST_STEP = STEP_PREVIEW;
export const COUNTED_STEPS = 5;

/** Normalize an out-of-range or non-numeric `:step` param to a real sheet. */
export function clampStep(raw: string | undefined): number {
  const parsed = Number(raw);
  if (!Number.isInteger(parsed)) return FIRST_STEP;
  return Math.min(Math.max(parsed, FIRST_STEP), LAST_STEP);
}

/** Volume units offered beside «Нужный объем». */
export const VOLUME_UNITS = ["MT", "KG"] as const;

/** Currencies beside «Проходная цена». Stored as `currency`; the "/ MT" is display. */
export const PRICE_CURRENCIES = ["USD", "UZS", "EUR", "RUB"] as const;

/**
 * Delivery timing tiles on sheet 2. Maps onto the backend `urgency` enum plus an
 * approximate `desired_date` so the staff side still sees a deadline.
 */
export const DELIVERY_BANDS = [
  { id: "urgent", urgency: "high", days: 7 },
  { id: "month", urgency: "medium", days: 30 },
  { id: "quarter", urgency: "low", days: 90 },
  { id: "later", urgency: "low", days: 180 },
] as const;

export type DeliveryBandId = (typeof DELIVERY_BANDS)[number]["id"];

export const DEFAULT_DELIVERY_BAND: DeliveryBandId = "month";

/** Validity period options for «Период действия заявки». */
export const VALIDITY_OPTIONS = [7, 14, 30, 60, 90] as const;

export const DEFAULT_VALIDITY_DAYS = 30;

/**
 * Destination countries for «Страна / Регион поставки» — ISO-3166 alpha-2, names
 * resolved through `Intl.DisplayNames` at render time.
 */
export const DEST_COUNTRIES = [
  "UZ",
  "KZ",
  "KG",
  "TJ",
  "TM",
  "RU",
  "TR",
  "CN",
  "AE",
] as const;

export const DEFAULT_DEST_COUNTRY = "UZ";

/**
 * City / port presets. Free-typed values still work — the select offers
 * «Другое» and a manual field, same escape hatch as the offer warehouse list.
 */
export const DEST_CITIES = [
  "Ташкент",
  "Самарканд",
  "Бухара",
  "Наманган",
  "Андижан",
  "Фергана",
  "Навои",
  "Карши",
  "Термез",
  "Нукус",
  "Ургенч",
  "Алматы",
  "Астана",
] as const;

export const OTHER_OPTION = "other";

/**
 * Document checklist on sheet 3. Not a backend column — selected kinds are
 * folded into `comment` at submit so staff still see the ask.
 */
export const REQUEST_DOC_KINDS = [
  "sds",
  "coa",
  "coo",
  "commercial",
  "other",
] as const;

export type RequestDocKind = (typeof REQUEST_DOC_KINDS)[number];

/** How the buyer wants to receive offers — UI preference, folded into comment. */
export const OFFER_CHANNELS = ["app", "email", "telegram"] as const;
export type OfferChannel = (typeof OFFER_CHANNELS)[number];

/** Who can see the request — UI preference, folded into comment. */
export const VISIBILITY_OPTIONS = ["verified", "all", "selected"] as const;
export type VisibilityOption = (typeof VISIBILITY_OPTIONS)[number];

export const SPECS_MAX = 300;
export const COMMENT_MAX = 300;
