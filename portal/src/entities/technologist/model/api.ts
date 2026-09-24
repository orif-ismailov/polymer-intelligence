import { api } from "@/shared/api";

import type {
  TechFacets,
  TechnologistCard,
  TechnologistCardList,
  TechnologistFilters,
  TechnologistOwnProfile,
  TechnologistProfileInput,
} from "./types";

/**
 * `/public/technologists` runs in BOTH environments — the SSR render and the
 * browser — so these stay free of anything browser-only, like `entities/public`.
 */
const PUBLIC = "/public/technologists";
const OWN = "/portal/me/technologist";

export const technologistKeys = {
  all: ["technologists"] as const,
  list: (filters: TechnologistFilters, offset: number, limit: number) =>
    ["technologists", "list", filters, offset, limit] as const,
  card: (id: number) => ["technologists", "card", id] as const,
  facets: () => ["technologists", "facets"] as const,
  own: () => ["technologists", "own"] as const,
  ownPhoto: () => ["technologists", "own-photo"] as const,
};

export function fetchTechnologists(
  filters: TechnologistFilters,
  offset: number,
  limit: number,
): Promise<TechnologistCardList> {
  return api.get<TechnologistCardList>(PUBLIC, {
    query: {
      process: filters.process || undefined,
      material: filters.material || undefined,
      language: filters.language || undefined,
      country: filters.country || undefined,
      q: filters.q || undefined,
      offset,
      limit,
    },
  });
}

export function fetchTechnologist(id: number): Promise<TechnologistCard> {
  return api.get<TechnologistCard>(`${PUBLIC}/${id}`);
}

export function fetchTechFacets(): Promise<TechFacets> {
  return api.get<TechFacets>(`${PUBLIC}/facets`);
}

export const technologistApi = {
  own: (): Promise<TechnologistOwnProfile> => api.get<TechnologistOwnProfile>(OWN),
  save: (payload: TechnologistProfileInput): Promise<TechnologistOwnProfile> =>
    api.put<TechnologistOwnProfile>(OWN, payload),
  submit: (): Promise<TechnologistOwnProfile> =>
    api.post<TechnologistOwnProfile>(`${OWN}/submit`),
  /** The expert's CURRENT portrait — behind the session, so an `<img src>`
   *  cannot fetch it (no Bearer header); it comes back as a Blob instead. */
  ownPhoto: (): Promise<Blob> => api.blob(`${OWN}/photo`),
  uploadPhoto: (file: File): Promise<TechnologistOwnProfile> => {
    const form = new FormData();
    form.append("file", file);
    return api.post<TechnologistOwnProfile>(`${OWN}/photo`, form);
  },
};
