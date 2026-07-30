import { api } from "@/shared/api";

import type { Product } from "./types";

export const productApi = {
  /** Active catalog rows, already ordered for the dropdown by the server. */
  list: (): Promise<Product[]> => api.get<Product[]>("/portal/reference/products"),
};

export const productKeys = {
  list: () => ["products"] as const,
};
