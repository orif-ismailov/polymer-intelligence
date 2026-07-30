import { useQuery } from "@tanstack/react-query";

import { productApi, productKeys } from "./api";
import type { Product } from "./types";

/**
 * The product catalog for the offer selectors.
 *
 * Reference data that changes when an admin edits it and not otherwise, so it is
 * cached for the session rather than refetched per mount — the wizard mounts it
 * on step 1 and reads it again on the preview sheet.
 */
export function useProducts() {
  return useQuery<Product[]>({
    queryKey: productKeys.list(),
    queryFn: productApi.list,
    staleTime: 30 * 60 * 1000,
  });
}

/** Localized product name, falling back to Russian (the catalog's only required name). */
export function productName(product: Product, lang: string): string {
  if (lang === "uz" && product.name_uz) return product.name_uz;
  if (lang === "en" && product.name_en) return product.name_en;
  return product.name_ru;
}

/** The dropdown label the mockups show — «Полипропилен (PP)». */
export function productLabel(product: Product, lang: string): string {
  return `${productName(product, lang)} (${product.code})`;
}
