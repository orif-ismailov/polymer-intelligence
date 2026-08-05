export { default as i18n, SUPPORTED_LANGS, DEFAULT_LANG, detectLanguage, preferredLanguage, coerceLang, setLanguage } from "./i18n";
export type { Lang } from "./i18n";
export {
  COMPANY_STATUS_TONE,
  CASE_STATUS_TONE,
  CHECK_STATUS_TONE,
  OFFER_STATUS_TONE,
  toneFor,
} from "./labels";
export { useEnumLabels } from "./useLabels";
