import type { BusinessRole } from "@/shared/config";
import type { CompanySummary } from "./types";

/**
 * The role → feature matrix: which cabinet features an account type gets.
 *
 * Single source of truth for the SideNav, the home module grid and the
 * `RequireFeature` route guard — the backend enforces the same sets
 * (`company_service.SELLER_ROLES` etc.), so hiding here is a courtesy and the
 * 403 is the law. Lives in `entities/company` (not the wizard's ACCOUNT_TYPES)
 * because the FSD import rule forbids entities/app reaching into features/.
 */
export type FeatureKey =
  /** Publish/manage sell offers — /cabinet/offers* */
  | "offers"
  /** Supplier RFQ inbox — /cabinet/market/requests */
  | "rfqInbox"
  /** Buyer purchase-request wizard/detail — /cabinet/requests/new*, /:id */
  | "purchaseRequests"
  /** Offer inquiries — /cabinet/inquiries* */
  | "inquiries"
  /** Sample requests — /cabinet/samples */
  | "samples"
  /** Factory chat + factory RFQ — /cabinet/manufacturers/* */
  | "factory"
  /** Order a lab analysis — /cabinet/lab/requests* (NOT lab/threads — that is the answering side's address) */
  | "labOrdering"
  /** Order shipping — /cabinet/logistics/requests* (NOT logistics/threads) */
  | "logisticsOrdering"
  /** Offer favorites — /cabinet/market/favorites */
  | "favorites"
  /** P6 partner-lab orders — /cabinet/lab-orders */
  | "labOrders";

const SELLER = ["manufacturer", "distributor", "trader"] as const satisfies readonly BusinessRole[];

/** Manufacturers keep the buy side — raw-material procurement is real. */
const BUYER_CAPABLE = [
  "importer",
  "distributor",
  "trader",
  "manufacturer",
] as const satisfies readonly BusinessRole[];

export const FEATURE_ROLES: Record<FeatureKey, readonly BusinessRole[]> = {
  offers: SELLER,
  rfqInbox: SELLER,
  purchaseRequests: BUYER_CAPABLE,
  inquiries: BUYER_CAPABLE,
  samples: BUYER_CAPABLE,
  factory: BUYER_CAPABLE,
  // Cross-service ordering is legitimate: a carrier tests cargo, a lab ships
  // samples. Only the company's OWN service side is closed to it.
  labOrdering: [...BUYER_CAPABLE, "logistics_provider"],
  logisticsOrdering: [...BUYER_CAPABLE, "laboratory"],
  favorites: BUYER_CAPABLE,
  labOrders: BUYER_CAPABLE,
};

/** Roles the matrix knows; `insurance_provider` (and future members) are not gateable. */
const GATEABLE: readonly string[] = [
  "importer",
  "distributor",
  "trader",
  "manufacturer",
  "logistics_provider",
  "laboratory",
];

/**
 * The declared (non-revoked) roles the matrix runs on. A company holding no
 * gateable roles — legacy rows, unknown members — reads as a buyer: fail OPEN
 * to the fullest non-seller view, same philosophy as `RequireCompany`.
 */
export function effectiveRoles(
  company: CompanySummary | null | undefined,
): readonly BusinessRole[] {
  const held = (company?.declared_roles ?? []).filter((r): r is BusinessRole =>
    GATEABLE.includes(r),
  );
  return held.length > 0 ? held : ["importer"];
}

export function companyHasFeature(
  company: CompanySummary | null | undefined,
  feature: FeatureKey,
): boolean {
  const roles = effectiveRoles(company);
  return FEATURE_ROLES[feature].some((allowed) => roles.includes(allowed));
}
