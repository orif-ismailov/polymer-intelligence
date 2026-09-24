import { useQuery } from "@tanstack/react-query";

import { contractApi, contractKeys } from "./api";
import type { ContractDetail, ContractSummary, ContractTemplate, TermPresetList } from "./types";

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

/** The company's saved terms. Off until a company is known. */
export function useTermPresets(companyId: number | null) {
  return useQuery<TermPresetList>({
    queryKey: contractKeys.termPresets(companyId ?? 0),
    queryFn: () => contractApi.termPresets(companyId as number),
    enabled: companyId != null,
  });
}
