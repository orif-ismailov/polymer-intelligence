import type {
  MissingRequirement,
  RegulationLevel,
  SubstanceBrief,
} from "@/entities/compliance";
import type { Availability, OfferStatus, SaleMode } from "@/shared/config";

/** A file attached to an offer — photo (`image`) or document. */
export interface OfferFile {
  id: number;
  /** `sds`/`coa` arrived with the compliance document list (P5);
   *  `lab_passport` with the laboratory badge (P6). */
  kind: "image" | "tds" | "certificate" | "other" | "sds" | "coa" | "lab_passport";
  file_name: string;
}

export interface OfferPayload {
  product_id?: number | null;
  product_text?: string | null;
  grade_text?: string | null;
  polymer_type?: string | null;
  availability: Availability;
  qty_available?: string | number | null;
  qty_unit: string;
  price?: string | number | null;
  currency: string;
  /** One of the Incoterm enum values; typed as string to tolerate unknowns. */
  incoterms: string;
  warehouse_city?: string | null;
  country?: string | null;
  min_order_qty?: string | number | null;
  description?: string | null;
  /** Product facts the add-product sheets collect. Who made the goods, and the
   *  two chip rows («Ключевые свойства» / «Применение»). */
  manufacturer?: string | null;
  key_properties?: string[];
  applications?: string[];
  /** Production/sourcing lead time. Required by the API for made-to-order offers. */
  lead_time_days?: number | null;
  sale_mode?: SaleMode | null;
  /** Deal-readiness flags → badges on the market card. */
  accepts_rfq: boolean;
  accepts_contract: boolean;
  accepts_escrow: boolean;
  /** Chemistry (P5). The registry link, or hand-typed identifiers. */
  substance_id?: number | null;
  cas_number?: string | null;
  hs_code?: string | null;
  declared_concentration_pct?: string | number | null;
  /** Sample terms (P6). A price without `samples_available` is rejected by the
   *  API — the card would promise something nobody can order. */
  samples_available?: boolean;
  sample_price?: string | number | null;
  sample_dispatch_days?: number | null;
}

export interface CompanyOffer extends OfferPayload {
  id: number;
  status: OfferStatus;
  moderation_note: string | null;
  created_at: string;
  /** Attached files in upload order. */
  files: OfferFile[];
  /** The first photo; null when the offer has none. */
  cover_file_id: number | null;
  /** The registry row itself, so an edit form shows what was picked. */
  substance?: SubstanceBrief | null;
  /**
   * Cached compliance verdict (P5). `compliance_ok === false` on a draft is WHY
   * it is a draft — the gate held it until the missing licence or document
   * exists.
   */
  compliance_level?: RegulationLevel | null;
  compliance_ok?: boolean | null;
  compliance_missing?: MissingRequirement[] | null;
  /** A passport is attached (anyone can upload one). */
  has_lab_passport?: boolean;
  /** We arranged the analysis — set only by a finished platform lab order. */
  lab_verified?: boolean;
}
