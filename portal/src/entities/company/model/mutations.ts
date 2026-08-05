import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/shared/api";

import { companyApi, companyKeys } from "./api";
import type {
  CompanyDetail,
  CompanyProfilePatch,
  CompanyReviewPayload,
  CompanyReviewResult,
  CreateBankAccountPayload,
  PublicProfilePatch,
} from "./types";

function useCompanyDetailMutation<TArgs>(
  companyId: number,
  fn: (args: TArgs) => Promise<CompanyDetail>,
) {
  const qc = useQueryClient();
  return useMutation<CompanyDetail, Error, TArgs>({
    mutationFn: fn,
    onSuccess: (detail) => {
      qc.setQueryData(companyKeys.detail(companyId), detail);
      void qc.invalidateQueries({ queryKey: companyKeys.list() });
    },
  });
}

export function useUpdateCompanyProfile(companyId: number) {
  return useCompanyDetailMutation<CompanyProfilePatch>(companyId, (patch) =>
    companyApi.updateProfile(companyId, patch),
  );
}

export function useUpdateCompanyPublicProfile(companyId: number) {
  return useCompanyDetailMutation<PublicProfilePatch>(companyId, (patch) =>
    companyApi.updatePublicProfile(companyId, patch),
  );
}

export function useUploadCompanyCover(companyId: number) {
  return useCompanyDetailMutation<File>(companyId, (file) =>
    companyApi.uploadCover(companyId, file),
  );
}

/**
 * Rate a counterparty.
 *
 * Not a `useCompanyDetailMutation`: that helper writes the response into the
 * COMPANY detail cache, and a review's response is a review. It invalidates the
 * public company query instead, which is where the aggregate lives.
 */
export function useSubmitCompanyReview(companyId: number) {
  const qc = useQueryClient();
  return useMutation<CompanyReviewResult, ApiError, CompanyReviewPayload>({
    mutationFn: (payload) => companyApi.submitReview(companyId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["public", "company"] });
    },
  });
}

export function useSetCompanyRoles(companyId: number) {
  return useCompanyDetailMutation<string[]>(companyId, (roles) =>
    companyApi.setRoles(companyId, roles),
  );
}

export function useAddBankAccount(companyId: number) {
  return useCompanyDetailMutation<CreateBankAccountPayload>(companyId, (payload) =>
    companyApi.addBankAccount(companyId, payload),
  );
}

export function useRemoveBankAccount(companyId: number) {
  return useCompanyDetailMutation<number>(companyId, (accountId) =>
    companyApi.removeBankAccount(companyId, accountId),
  );
}

export function useUploadCompanyDocument(companyId: number) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { kind: string; file: File }>({
    mutationFn: ({ kind, file }) => companyApi.uploadDocument(companyId, kind, file),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: companyKeys.detail(companyId) });
    },
  });
}

export function useRemoveCompanyDocument(companyId: number) {
  const qc = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: (documentId) => companyApi.removeDocument(companyId, documentId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: companyKeys.detail(companyId) });
    },
  });
}
