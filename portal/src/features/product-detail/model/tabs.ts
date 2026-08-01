/**
 * The product sheet's tab rail, in mockup order
 * (`docs/new-design/product_detail.jpeg`).
 *
 * Shared so the cabinet and the storefront show the same five entries with the
 * same labels (`market.tabs.*`). `compatibility` and `reviews` are chrome for
 * surfaces that are not built yet.
 */
export const PRODUCT_DETAIL_TAB_IDS = [
  "description",
  "specs",
  "documents",
  "compatibility",
  "reviews",
] as const;

export type ProductDetailTabId = (typeof PRODUCT_DETAIL_TAB_IDS)[number];
