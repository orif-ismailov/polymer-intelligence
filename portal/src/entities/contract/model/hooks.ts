import { useQuery } from "@tanstack/react-query";

import { contractApi, contractKeys } from "./api";
import type { ContractDetail, ContractSummary, ContractTemplate } from "./types";

export function useContractTemplates() {
  return useQuery<ContractTemplate[]>({
    queryKey: contractKeys.templates(),
    queryFn: () => contractApi.templates(),
  });
}

export function useContracts(params: { company_id?: number; status?: string } = {}) {
  return useQuery<ContractSummary[]>({
    queryKey: contractKeys.list(params),
    queryFn: () => contractApi.list(params),
  });
}

export function useContract(id: number | null) {
  return useQuery<ContractDetail>({
    queryKey: contractKeys.detail(id ?? 0),
    queryFn: () => contractApi.get(id as number),
    enabled: id != null,
  });
}
