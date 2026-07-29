import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { inquiryApi, inquiryKeys } from "./api";
import type { Inquiry, InquiryPayload } from "./types";

export function useSentInquiries(companyId: number | null) {
  return useQuery<Inquiry[]>({
    queryKey: inquiryKeys.sent(companyId ?? -1),
    queryFn: () => inquiryApi.listSent(companyId as number),
    enabled: companyId != null,
  });
}

export function useIncomingInquiries(companyId: number | null) {
  return useQuery<Inquiry[]>({
    queryKey: inquiryKeys.incoming(companyId ?? -1),
    queryFn: () => inquiryApi.listIncoming(companyId as number),
    enabled: companyId != null,
  });
}

export function useInquiry(inquiryId: number | null) {
  return useQuery<Inquiry>({
    queryKey: inquiryKeys.detail(inquiryId ?? -1),
    queryFn: () => inquiryApi.get(inquiryId as number),
    enabled: inquiryId != null,
  });
}

/** Create an inquiry against an offer, then refresh the company's sent list. */
export function useCreateInquiry(companyId: number | null) {
  const qc = useQueryClient();
  return useMutation<Inquiry, Error, { offerId: number; payload: InquiryPayload }>({
    mutationFn: ({ offerId, payload }) => inquiryApi.create(offerId, payload),
    onSuccess: () => {
      if (companyId != null) {
        void qc.invalidateQueries({ queryKey: inquiryKeys.sent(companyId) });
      }
    },
  });
}

/** Revise a sent inquiry (re-enters moderation); refresh detail + lists. */
export function useUpdateInquiry(companyId: number | null) {
  const qc = useQueryClient();
  return useMutation<Inquiry, Error, { inquiryId: number; payload: InquiryPayload }>({
    mutationFn: ({ inquiryId, payload }) => inquiryApi.update(inquiryId, payload),
    onSuccess: (inquiry) => {
      qc.setQueryData(inquiryKeys.detail(inquiry.id), inquiry);
      if (companyId != null) {
        void qc.invalidateQueries({ queryKey: inquiryKeys.sent(companyId) });
      }
    },
  });
}
