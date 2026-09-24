import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/shared/api";

import { techRequestApi, techRequestKeys } from "./api";
import type {
  CompanyOffer,
  TechFeedItem,
  TechOfferInput,
  TechRequest,
  TechRequestInput,
  TechReview,
} from "./types";

/** Same cadence as every other chat — one expectation of "live". */
export const TECH_CHAT_POLL_MS = 15_000;

// ── The factory ───────────────────────────────────────────────────────────────

export function useCompanyTechRequests(companyId: number | null) {
  return useQuery<TechRequest[]>({
    queryKey: techRequestKeys.companyList(companyId),
    queryFn: () => techRequestApi.list(companyId as number).then((r) => r.items),
    enabled: companyId != null,
  });
}

export function useCompanyTechRequest(companyId: number | null, id: number | null) {
  return useQuery<TechRequest, ApiError>({
    queryKey: techRequestKeys.companyDetail(companyId, id),
    queryFn: () => techRequestApi.get(companyId as number, id as number),
    enabled: companyId != null && id != null,
  });
}

export function useCompanyTechOffers(companyId: number | null, id: number | null) {
  return useQuery<CompanyOffer[]>({
    queryKey: techRequestKeys.offers(companyId, id),
    queryFn: () => techRequestApi.offers(companyId as number, id as number).then((r) => r.items),
    enabled: companyId != null && id != null,
  });
}

export function useTechReview(companyId: number | null, id: number | null, enabled: boolean) {
  return useQuery<TechReview | null>({
    queryKey: techRequestKeys.review(companyId, id),
    queryFn: () => techRequestApi.review(companyId as number, id as number),
    enabled: enabled && companyId != null && id != null,
  });
}

/** Any factory-side write invalidates everything about requests — they are few. */
function useCompanyMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation<TResult, ApiError, TVars>({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: techRequestKeys.all });
    },
  });
}

export function useCreateTechRequest(companyId: number | null) {
  return useCompanyMutation<TechRequestInput, TechRequest>((payload) =>
    techRequestApi.create(companyId as number, payload),
  );
}

export function useCancelTechRequest(companyId: number | null, id: number | null) {
  return useCompanyMutation<void, TechRequest>(() =>
    techRequestApi.cancel(companyId as number, id as number),
  );
}

export function useDecideTechOffer(companyId: number | null, id: number | null) {
  return useCompanyMutation<{ offerId: number; accept: boolean }, TechRequest>(
    ({ offerId, accept }) =>
      accept
        ? techRequestApi.accept(companyId as number, id as number, offerId)
        : techRequestApi.decline(companyId as number, id as number, offerId),
  );
}

export function useCompleteTechRequest(companyId: number | null, id: number | null) {
  return useCompanyMutation<{ rating: number; text: string | null }, TechReview>((body) =>
    techRequestApi.complete(companyId as number, id as number, body),
  );
}

export function useInviteTechnologist(companyId: number | null) {
  return useCompanyMutation<{ requestId: number; profileId: number }, void>(
    ({ requestId, profileId }) =>
      techRequestApi.invite(companyId as number, requestId, profileId),
  );
}

// ── The expert ────────────────────────────────────────────────────────────────

export function useTechFeed(invited: boolean, enabled = true) {
  return useQuery<TechFeedItem[]>({
    queryKey: techRequestKeys.feed(invited),
    queryFn: () => techRequestApi.feed(invited).then((r) => r.items),
    enabled,
  });
}

export function useTechFeedItem(id: number | null) {
  return useQuery<TechFeedItem, ApiError>({
    queryKey: techRequestKeys.feedItem(id),
    queryFn: () => techRequestApi.feedItem(id as number),
    enabled: id != null,
  });
}

/** Offer / change / withdraw — each answers with the refreshed feed item. */
export function useTechOfferAction(id: number) {
  const queryClient = useQueryClient();
  return useMutation<
    TechFeedItem,
    ApiError,
    { action: "submit" | "update"; payload: TechOfferInput } | { action: "withdraw" }
  >({
    mutationFn: (vars) => {
      if (vars.action === "withdraw") return techRequestApi.withdrawOffer(id);
      return vars.action === "submit"
        ? techRequestApi.submitOffer(id, vars.payload)
        : techRequestApi.updateOffer(id, vars.payload);
    },
    onSuccess: (item) => {
      queryClient.setQueryData(techRequestKeys.feedItem(id), item);
      void queryClient.invalidateQueries({ queryKey: ["tech-requests", "feed"] });
    },
  });
}

export function useOpenExpertThread(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => techRequestApi.openThreadAsExpert(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: techRequestKeys.feedItem(id) });
    },
  });
}

export function useOpenCompanyThread(companyId: number | null, id: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profileId: number) =>
      techRequestApi.openThreadAsCompany(companyId as number, id as number, profileId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: techRequestKeys.offers(companyId, id) });
    },
  });
}
