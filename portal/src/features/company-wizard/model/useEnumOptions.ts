import { useMemo } from "react";

import { useEnumLabels } from "@/shared/i18n";
import type { SelectOption } from "@/shared/ui";

/** Build translated <Select> options from an enum value array. */
export function useEnumOptions(namespace: string, values: readonly string[]): SelectOption[] {
  const label = useEnumLabels();
  return useMemo(
    () => values.map((value) => ({ value, label: label(namespace, value) })),
    [namespace, values, label],
  );
}
