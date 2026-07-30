import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/shared/api";

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

/**
 * Create an inquiry against an offer, then refresh the company's sent list.
 *
 * The market caches go too: the offer detail carries `my_inquiries`, so without
 * this the buyer sends an inquiry and the «Мои запросы» card on the very page
 * they are looking at stays empty until a reload.
 */
export function useCreateInquiry(companyId: number | null) {
  const qc = useQueryClient();
  return useMutation<Inquiry, ApiError, { offerId: number; payload: InquiryPayload }>({
    mutationFn: ({ offerId, payload }) => inquiryApi.create(offerId, payload),
    onSuccess: () => {
      if (companyId != null) {
        void qc.invalidateQueries({ queryKey: inquiryKeys.sent(companyId) });
      }
      void qc.invalidateQueries({ queryKey: ["market"] });
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
