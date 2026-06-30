/**
 * useProducts — loads the active polymer products from the backend
 * (GET /webapp/reference/products) once and caches them module-wide, so the
 * buyer/seller selectors, the catalog chips, and the offer cards share one
 * admin-managed list instead of hardcoded arrays.
 */

import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Product } from "../types";

let cache: Product[] | null = null;
let inflight: Promise<Product[]> | null = null;

function load(): Promise<Product[]> {
  if (cache) return Promise.resolve(cache);
  if (!inflight) {
    inflight = api
      .getProducts()
      .then((p) => {
        cache = p;
        return p;
      })
      .catch(() => {
        inflight = null; // allow a retry on the next mount
        return [];
      });
  }
  return inflight;
}

export function useProducts(): { products: Product[]; loading: boolean } {
  const [products, setProducts] = useState<Product[]>(cache ?? []);
  const [loading, setLoading] = useState<boolean>(cache === null);

  useEffect(() => {
    if (cache) return;
    let cancelled = false;
    void load().then((p) => {
      if (!cancelled) {
        setProducts(p);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { products, loading };
}

/** Localized product name for the active language, falling back to RU. */
export function productName(p: Product, lang: string): string {
  if (lang === "uz" && p.name_uz) return p.name_uz;
  if (lang === "en" && p.name_en) return p.name_en;
  if (lang === "tr" && p.name_tr) return p.name_tr;
  return p.name_ru;
}
