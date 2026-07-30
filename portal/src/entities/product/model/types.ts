/** The polymer catalog behind «Название товара» (`GET /portal/reference/products`). */
export interface Product {
  id: number;
  /** Short code the market speaks in — "PP", "HDPE". */
  code: string;
  name_ru: string;
  name_uz: string | null;
  name_en: string | null;
  name_tr: string | null;
  category: string;
  sort_order: number;
  is_active: boolean;
}

/**
 * The sentinel option for "not in the catalog".
 *
 * A string, not a number, because the `<select>` value is a string either way
 * and comparing `"other"` to a stringified id can never collide — the ids are
 * numerals.
 */
export const PRODUCT_OTHER = "other";
