import { useCallback, useState } from "react";

import type { CompanyOffer, OfferPayload } from "@/entities/offer";
import type { Availability, SaleMode } from "@/shared/config";

export interface OfferFormState {
  product_text: string;
  grade_text: string;
  polymer_type: string;
  availability: Availability;
  qty_available: string;
  qty_unit: string;
  price: string;
  currency: string;
  incoterms: string;
  warehouse_city: string;
  country: string;
  min_order_qty: string;
  description: string;
  lead_time_days: string;
  sale_mode: string;
  accepts_rfq: boolean;
  accepts_contract: boolean;
  accepts_escrow: boolean;
}

export interface OfferFormErrors {
  product_text?: string;
  qty_unit?: string;
  lead_time_days?: string;
}

export const EMPTY_OFFER_FORM: OfferFormState = {
  product_text: "",
  grade_text: "",
  polymer_type: "",
  availability: "in_stock",
  qty_available: "",
  qty_unit: "t",
  price: "",
  currency: "UZS",
  incoterms: "EXW",
  warehouse_city: "",
  country: "",
  min_order_qty: "",
  description: "",
  lead_time_days: "",
  sale_mode: "",
  // Mirrors the backend defaults: answering an RFQ costs nothing, a contract and
  // escrow are commitments the seller opts into.
  accepts_rfq: true,
  accepts_contract: false,
  accepts_escrow: false,
};

/** Seed the form state from an existing offer (edit mode). */
export function offerToForm(offer: CompanyOffer): OfferFormState {
  return {
    product_text: offer.product_text ?? "",
    grade_text: offer.grade_text ?? "",
    polymer_type: offer.polymer_type ?? "",
    availability: offer.availability,
    qty_available: offer.qty_available != null ? String(offer.qty_available) : "",
    qty_unit: offer.qty_unit,
    price: offer.price != null ? String(offer.price) : "",
    currency: offer.currency,
    incoterms: offer.incoterms,
    warehouse_city: offer.warehouse_city ?? "",
    country: offer.country ?? "",
    min_order_qty: offer.min_order_qty != null ? String(offer.min_order_qty) : "",
    description: offer.description ?? "",
    lead_time_days: offer.lead_time_days != null ? String(offer.lead_time_days) : "",
    sale_mode: offer.sale_mode ?? "",
    accepts_rfq: offer.accepts_rfq,
    accepts_contract: offer.accepts_contract,
    accepts_escrow: offer.accepts_escrow,
  };
}

function trimOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/** Convert validated form state into the API payload. */
export function formToPayload(state: OfferFormState): OfferPayload {
  return {
    product_text: trimOrNull(state.product_text),
    grade_text: trimOrNull(state.grade_text),
    polymer_type: trimOrNull(state.polymer_type),
    availability: state.availability,
    qty_available: trimOrNull(state.qty_available),
    qty_unit: state.qty_unit,
    price: trimOrNull(state.price),
    currency: state.currency,
    incoterms: state.incoterms,
    warehouse_city: trimOrNull(state.warehouse_city),
    country: trimOrNull(state.country),
    min_order_qty: trimOrNull(state.min_order_qty),
    description: trimOrNull(state.description),
    lead_time_days: state.lead_time_days.trim() === "" ? null : Number(state.lead_time_days),
    // The select carries "" for "not stated"; anything else is a SaleMode by
    // construction (the options come from SALE_MODES).
    sale_mode: state.sale_mode === "" ? null : (state.sale_mode as SaleMode),
    accepts_rfq: state.accepts_rfq,
    accepts_contract: state.accepts_contract,
    accepts_escrow: state.accepts_escrow,
  };
}

export function validateOfferForm(state: OfferFormState): OfferFormErrors {
  const errors: OfferFormErrors = {};
  if (state.product_text.trim() === "") errors.product_text = "offers.productTextRequired";
  if (state.qty_unit.trim() === "") errors.qty_unit = "offers.qtyUnitRequired";
  // A made-to-order offer carries no price ("по запросу"), so without a lead time
  // the card tells a buyer nothing they can plan around. The API refuses it too —
  // this just says so before the round trip.
  if (state.availability === "on_order" && state.lead_time_days.trim() === "") {
    errors.lead_time_days = "offers.leadTimeRequired";
  }
  return errors;
}

/** Local form-state controller for the offer form. */
export function useOfferForm(initial: OfferFormState) {
  const [state, setState] = useState<OfferFormState>(initial);
  const [errors, setErrors] = useState<OfferFormErrors>({});

  const setField = useCallback(<K extends keyof OfferFormState>(key: K, value: OfferFormState[K]) => {
    setState((prev) => ({ ...prev, [key]: value }));
  }, []);

  const validate = useCallback((): boolean => {
    const next = validateOfferForm(state);
    setErrors(next);
    return Object.keys(next).length === 0;
  }, [state]);

  return { state, errors, setField, validate };
}
