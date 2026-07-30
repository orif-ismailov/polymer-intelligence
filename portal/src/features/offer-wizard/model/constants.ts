/**
 * The add-product flow, sheet for sheet (`docs/new-design/product_creation.jpeg`).
 *
 * Seven collecting sheets, then the preview and the published sheet — which are
 * NOT steps 8 and 9 of the rail: the mockup's rail ends at «Публикация», and the
 * preview is what that step looks like before you press the button.
 */

export const STEP_BASICS = 1;
export const STEP_AI_CHECK = 2;
export const STEP_AVAILABILITY = 3;
export const STEP_DOCUMENTS = 4;
export const STEP_LAB = 5;
export const STEP_TERMS = 6;
export const STEP_EXTRA = 7;
/** The «Публикация» rail step: the preview sheet and its green CTA. */
export const STEP_PREVIEW = 8;

export const FIRST_STEP = STEP_BASICS;
export const LAST_STEP = STEP_PREVIEW;
/** What «Шаг N из 7» counts — the collecting sheets, not the preview. */
export const COUNTED_STEPS = STEP_EXTRA;

/** Normalize an out-of-range or non-numeric `:step` param to a real sheet. */
export function clampStep(raw: string | undefined): number {
  const parsed = Number(raw);
  if (!Number.isInteger(parsed)) return FIRST_STEP;
  return Math.min(Math.max(parsed, FIRST_STEP), LAST_STEP);
}

/**
 * Origin countries offered by «Страна происхождения», as ISO-3166 alpha-2 —
 * `seller_offers.country` is a `char(2)` column, so a label can never be the
 * stored value. Names are resolved at render time through `Intl.DisplayNames`
 * rather than a translation table nobody would keep in sync.
 *
 * The list is the polymer trade Uzbekistan actually buys from, plus the majors;
 * a country outside it is still editable on an existing offer, because the
 * select offers an unrecognised value back as its own option.
 */
export const ORIGIN_COUNTRIES = [
  "UZ",
  "RU",
  "KZ",
  "TM",
  "AZ",
  "IR",
  "TR",
  "CN",
  "KR",
  "IN",
  "SA",
  "AE",
  "DE",
  "US",
] as const;

export const DEFAULT_ORIGIN_COUNTRY = "UZ";

/**
 * «Склад / Местоположение». The value IS the stored string (`warehouse_city` is
 * free text and the market list already holds these spellings), so the i18n key
 * only moves the label — changing a member here changes what new offers store.
 */
export const WAREHOUSE_LOCATIONS = [
  "Ташкент",
  "Ташкентская область",
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
  "Джизак",
  "Гулистан",
] as const;

/** The sentinel that reveals a free-text field, shared by both selects. */
export const OTHER_OPTION = "other";

/**
 * «Производитель» on sheet 1 — the mockup paints a select with «Sibur», not a
 * free-text box. The list is the makers Uzbekistan's polymer trade actually
 * names; anything outside it still lands through «Другое».
 */
export const MANUFACTURERS = [
  "Sibur",
  "Shurtan GCC",
  "Uz-Kor Gas Chemical",
  "Indorama",
  "Lukoil",
  "Gazprom Neftekhim Salavat",
  "Nizhnekamskneftekhim",
  "Sinopec",
  "SABIC",
  "Borouge",
  "LyondellBasell",
  "ExxonMobil",
  "Dow",
  "BASF",
] as const;

/**
 * «Срок отгрузки» — the mockup's «3–7 дней».
 *
 * The stored `lead_time_days` is the UPPER bound of the chosen band: a buyer
 * planning around a range plans around its worst case, and promising the lower
 * one is how a card becomes a complaint.
 */
export const DISPATCH_BANDS = [
  { id: "1-2", days: 2 },
  { id: "3-7", days: 7 },
  { id: "7-14", days: 14 },
  { id: "14-30", days: 30 },
  { id: "30-60", days: 60 },
] as const;

export type DispatchBandId = (typeof DISPATCH_BANDS)[number]["id"];

export const DEFAULT_DISPATCH_BAND: DispatchBandId = "3-7";

/** «Срок отправки» of a sample. Same upper-bound rule as the dispatch band. */
export const SAMPLE_BANDS = [
  { id: "1-3", days: 3 },
  { id: "3-7", days: 7 },
  { id: "7-14", days: 14 },
] as const;

export type SampleBandId = (typeof SAMPLE_BANDS)[number]["id"];

export const DEFAULT_SAMPLE_BAND: SampleBandId = "1-3";

/** Pick the band whose upper bound matches, so edit mode reopens on the right one. */
export function bandForDays<T extends { id: string; days: number }>(
  bands: readonly T[],
  days: number | null,
  fallback: T["id"],
): T["id"] {
  if (days == null) return fallback;
  const exact = bands.find((band) => band.days === days);
  if (exact) return exact.id;
  // An offer edited elsewhere (or by the Mini App) may carry a value no band
  // names. Round UP to the first band that still covers it rather than silently
  // shortening the seller's promise; past the widest band, take the widest.
  const covering = bands.find((band) => band.days >= days) ?? bands.at(-1);
  return covering?.id ?? fallback;
}

/** The three documents the «Документы» sheet asks for, in its order. */
export const OFFER_DOCUMENT_KINDS = ["sds", "tds", "coa"] as const;
export type OfferDocumentKind = (typeof OFFER_DOCUMENT_KINDS)[number];

/** Only COA is optional on the sheet («если есть»). */
export const REQUIRED_DOCUMENT_KINDS: readonly OfferDocumentKind[] = ["sds", "tds"];

/** Mirrors the server cap for offer files. */
export const MAX_PHOTOS = 8;

export const PHOTO_MIME = ["image/jpeg", "image/png"];
export const DOCUMENT_MIME = "application/pdf,image/jpeg,image/png";
/** A laboratory passport is a PDF — `lab_service.RESULT_MIME` says so too. */
export const PASSPORT_MIME = "application/pdf";

/** The four trust chips in the mockup's masthead. */
export const TRUST_CHIPS = ["safe", "legal", "professional", "international"] as const;

/** The five reassurance blocks along the mockup's footer. */
export const ASSURANCE_BLOCKS = ["deals", "trade", "lab", "b2b", "global"] as const;
