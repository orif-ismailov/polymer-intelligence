import { useQuery } from "@tanstack/react-query";

import { didoxApi } from "./api";

export const didoxStatusKey = (companyId: number | null) =>
  ["didox", "status", companyId] as const;

/** Where a company stands with Didox. One key, so every surface refreshes together. */
export function useDidoxStatus(companyId: number | null) {
  return useQuery({
    queryKey: didoxStatusKey(companyId),
    queryFn: () => didoxApi.status(companyId as number),
    enabled: companyId != null,
  });
}
