import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { companyKeys } from "@/entities/company";

import { verificationApi, verificationKeys } from "./api";
import type { CaseOut } from "./types";

/** Fetch the active verification case for a company. */
export function useVerificationCase(companyId: number | null) {
  return useQuery({
    queryKey: verificationKeys.detail(companyId ?? -1),
    queryFn: () => verificationApi.get(companyId as number),
    enabled: companyId != null,
  });
}

/** Submit a company for verification, refreshing case + company detail. */
export function useSubmitVerification(companyId: number) {
  const qc = useQueryClient();
  return useMutation<CaseOut, Error, void>({
    mutationFn: () => verificationApi.submit(companyId),
    onSuccess: (caseOut) => {
      qc.setQueryData(verificationKeys.detail(companyId), caseOut);
      void qc.invalidateQueries({ queryKey: companyKeys.detail(companyId) });
      void qc.invalidateQueries({ queryKey: companyKeys.list() });
    },
  });
}
