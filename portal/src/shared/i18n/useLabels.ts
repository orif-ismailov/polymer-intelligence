import { useTranslation } from "react-i18next";

/**
 * Enum-label resolver. Maps a namespaced enum value to its localized label via
 * i18n keys (e.g. `companyStatus.verified`). Falls back to the raw value if a
 * translation is missing, so unknown backend values never render blank.
 */
export function useEnumLabels() {
  const { t } = useTranslation();
  return (namespace: string, value: string): string => {
    const key = `${namespace}.${value}`;
    const label = t(key);
    return label === key ? value : label;
  };
}
