import { useMutation, useQueryClient } from "@tanstack/react-query";

import { contractApi, contractKeys } from "@/entities/contract";
import type { TermPreset, TermPresetPayload } from "@/entities/contract";

interface SaveArgs {
  presetId?: number | null;
  payload: TermPresetPayload;
}

/** Create or edit a preset; refreshes the company's list either way. */
export function useSaveTermPreset(companyId: number) {
  const queryClient = useQueryClient();
  return useMutation<TermPreset, unknown, SaveArgs>({
    mutationFn: ({ presetId, payload }) =>
      presetId != null
        ? contractApi.updateTermPreset(companyId, presetId, payload)
        : contractApi.createTermPreset(companyId, payload),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: contractKeys.termPresets(companyId),
      }),
  });
}

/** Archive a preset — contracts drawn up from it keep their own copy. */
export function useArchiveTermPreset(companyId: number) {
  const queryClient = useQueryClient();
  return useMutation<void, unknown, number>({
    mutationFn: (presetId) =>
      contractApi.archiveTermPreset(companyId, presetId),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: contractKeys.termPresets(companyId),
      }),
  });
}
