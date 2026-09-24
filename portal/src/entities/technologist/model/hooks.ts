import { useEffect } from "react";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import type { ApiError } from "@/shared/api";

import {
  fetchTechFacets,
  fetchTechnologist,
  fetchTechnologists,
  technologistApi,
  technologistKeys,
} from "./api";
import type {
  TechFacets,
  TechnologistCard,
  TechnologistCardList,
  TechnologistFilters,
  TechnologistOwnProfile,
  TechnologistProfileInput,
} from "./types";

const STALE = 60_000;

export function useTechnologists(
  filters: TechnologistFilters,
  offset: number,
  limit: number,
): UseQueryResult<TechnologistCardList> {
  return useQuery({
    queryKey: technologistKeys.list(filters, offset, limit),
    queryFn: () => fetchTechnologists(filters, offset, limit),
    staleTime: STALE,
    placeholderData: keepPreviousData,
  });
}

export function useTechnologist(id: number | null): UseQueryResult<TechnologistCard> {
  return useQuery({
    queryKey: technologistKeys.card(id ?? 0),
    queryFn: () => fetchTechnologist(id as number),
    enabled: id != null,
    staleTime: STALE,
  });
}

/** The closed vocabularies. They change with a deploy, not with data. */
export function useTechFacets(): UseQueryResult<TechFacets> {
  return useQuery({
    queryKey: technologistKeys.facets(),
    queryFn: fetchTechFacets,
    staleTime: Infinity,
  });
}

/**
 * The signed-in expert's own profile. `enabled` is the caller's: it must stay
 * false during SSR and for a company account (which the API answers 403).
 */
export function useOwnTechnologist(enabled = true): UseQueryResult<TechnologistOwnProfile, ApiError> {
  return useQuery<TechnologistOwnProfile, ApiError>({
    queryKey: technologistKeys.own(),
    queryFn: technologistApi.own,
    enabled,
  });
}

function useOwnMutation<TVars>(fn: (vars: TVars) => Promise<TechnologistOwnProfile>) {
  const queryClient = useQueryClient();
  return useMutation<TechnologistOwnProfile, ApiError, TVars>({
    mutationFn: fn,
    onSuccess: (profile) => {
      queryClient.setQueryData(technologistKeys.own(), profile);
    },
  });
}

export function useSaveTechnologist() {
  return useOwnMutation<TechnologistProfileInput>((payload) => technologistApi.save(payload));
}

export function useSubmitTechnologist() {
  return useOwnMutation<void>(() => technologistApi.submit());
}

export function useUploadTechnologistPhoto() {
  const queryClient = useQueryClient();
  const mutation = useOwnMutation<File>((file) => technologistApi.uploadPhoto(file));
  return {
    ...mutation,
    mutate: (file: File) =>
      mutation.mutate(file, {
        onSuccess: () => {
          void queryClient.invalidateQueries({ queryKey: technologistKeys.ownPhoto() });
        },
      }),
  };
}

/**
 * An object URL for the expert's own portrait, or null. Fetched through the
 * API client (with the token) because the route is private; revoked when it is
 * replaced so a session of re-uploads does not leak blobs.
 */
export function useOwnTechnologistPhoto(hasPhoto: boolean): string | null {
  const query = useQuery({
    queryKey: technologistKeys.ownPhoto(),
    queryFn: async () => URL.createObjectURL(await technologistApi.ownPhoto()),
    enabled: hasPhoto,
    staleTime: Infinity,
  });
  const url = query.data ?? null;
  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);
  return hasPhoto ? url : null;
}
