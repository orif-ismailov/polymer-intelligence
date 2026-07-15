/**
 * Seller-offer domain helpers shared by the create (SellOffer) and edit (EditOffer) forms.
 */

import type { OfferAvailability } from "../types";

/**
 * Whether an offer with the given availability needs a physical location
 * (`warehouse_city`).
 *
 * Goods «в наличии» (in_stock) sit at a warehouse and must declare where.
 * Goods «под заказ» (on_order, "By Order") are made/sourced on demand and have
 * no location yet — the location fields are hidden and never submitted.
 *
 * Single source of truth for this rule so the create and edit forms can't drift.
 */
export function availabilityRequiresLocation(availability: OfferAvailability): boolean {
  return availability === "in_stock";
}
