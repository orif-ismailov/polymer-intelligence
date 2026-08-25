import { create } from "zustand";

import type { IkpuValue } from "@/features/ikpu-picker";

import type { SubstanceBrief } from "@/entities/compliance";
import type { CompanyOffer, OfferFile, OfferPayload } from "@/entities/offer";
import { PRODUCT_OTHER } from "@/entities/product";
import type { Availability, SaleMode } from "@/shared/config";

import {
  DEFAULT_DISPATCH_BAND,
  DEFAULT_ORIGIN_COUNTRY,
  DEFAULT_SAMPLE_BAND,
  DISPATCH_BANDS,
  OTHER_OPTION,
  SAMPLE_BANDS,
  WAREHOUSE_LOCATIONS,
  bandForDays,
  type DispatchBandId,
  type OfferDocumentKind,
  type SampleBandId,
} from "./constants";

/** How the seller charges for a sample — the mockup's «Бесплатно / Платно». */
export type SampleFee = "free" | "paid";

export interface OfferDraft {
  // ── 1. Основная информация ────────────────────────────────────────────────
  /** A stringified product id, `"other"`, or "" — the raw `<select>` value. */
  productChoice: string;
  /** Typed name, live only while `productChoice === "other"`. */
  productText: string;
  gradeText: string;
  casNumber: string;
  hsCode: string;
  manufacturer: string;
  originCountry: string;
  category: string;
  // ── 2. AI проверка ────────────────────────────────────────────────────────
  /** Registry row the check settled on. Null when nothing matched. */
  substance: SubstanceBrief | null;
  /** Only asked for when the verdict says the regime is concentration-dependent. */
  concentration: string;
  // ── 3. Наличие / Под заказ ────────────────────────────────────────────────
  availability: Availability;
  qty: string;
  qtyUnit: string;
  price: string;
  currency: string;
  incoterms: string;
  minOrderQty: string;
  /** A `WAREHOUSE_LOCATIONS` member, or `"other"`. */
  warehouseChoice: string;
  warehouseOther: string;
  dispatchBand: DispatchBandId;
  // ── 5. Лабораторные данные ────────────────────────────────────────────────
  hasPassport: boolean;
  // ── 6. Условия продажи ────────────────────────────────────────────────────
  samplesAvailable: boolean;
  sampleFee: SampleFee;
  samplePrice: string;
  /**
   * Whether a buyer must e-sign a письмо-обязательство before this seller ships a
   * sample, and the consequence clause THIS seller writes for it (P7.a W8).
   *
   * Per-offer, not per-company: a seller may give away a 200 g pouch and still
   * demand a commitment for a 25 kg bag. The terms are snapshotted into the
   * letter at signing, so editing them later never rewrites a signed one.
   */
  sampleLetterRequired: boolean;
  sampleLetterTerms: string;
  /**
   * The goods' tax classification (P7.a W9).
   *
   * Chosen once here and reused by every «Договор НК» and ЭСФ this offer backs.
   * `null` is a permanent, legitimate state — an offer without it simply cannot
   * back a Didox document, and says so at contract time rather than being
   * back-filled with a guess.
   */
  ikpu: IkpuValue | null;
  sampleBand: SampleBandId;
  acceptsRfq: boolean;
  acceptsContract: boolean;
  acceptsEscrow: boolean;
  saleMode: string;
  // ── 7. Дополнительная информация ──────────────────────────────────────────
  description: string;
  keyProperties: string[];
  applications: string[];
}

/** A file the seller chose that has not been uploaded yet. */
export interface StagedFile {
  file: File;
  /** Object URL for the photo preview; revoked when the entry is dropped. */
  previewUrl: string | null;
}

interface DraftState {
  draft: OfferDraft;
  /** Set in edit mode; null while creating. */
  offerId: number | null;
  /** Photos not yet uploaded, in the order they will be — the first is the cover. */
  photos: StagedFile[];
  /** One staged document per kind; a kind already on the server stays absent. */
  documents: Partial<Record<OfferDocumentKind, StagedFile>>;
  labPassport: StagedFile | null;
  /** Files that exist server-side, shown as-is in edit mode. */
  serverFiles: OfferFile[];
  /** Ids of server files the seller removed — deleted when the sheet is submitted. */
  removedFileIds: number[];
  setField: <K extends keyof OfferDraft>(key: K, value: OfferDraft[K]) => void;
  patch: (patch: Partial<OfferDraft>) => void;
  addPhotos: (files: File[]) => void;
  removePhoto: (index: number) => void;
  setDocument: (kind: OfferDocumentKind, file: File | null) => void;
  setLabPassport: (file: File | null) => void;
  removeServerFile: (fileId: number) => void;
  /** Seed the whole store from an existing offer (edit mode). */
  hydrate: (offer: CompanyOffer) => void;
  reset: () => void;
}

export const EMPTY_DRAFT: OfferDraft = {
  productChoice: "",
  productText: "",
  gradeText: "",
  casNumber: "",
  hsCode: "",
  manufacturer: "",
  originCountry: DEFAULT_ORIGIN_COUNTRY,
  category: "",
  substance: null,
  concentration: "",
  availability: "in_stock",
  qty: "",
  qtyUnit: "MT",
  // USD, not UZS: every price on the mockups is in dollars, and so is the
  // backend column default.
  price: "",
  currency: "USD",
  incoterms: "EXW",
  minOrderQty: "",
  warehouseChoice: WAREHOUSE_LOCATIONS[0],
  warehouseOther: "",
  dispatchBand: DEFAULT_DISPATCH_BAND,
  hasPassport: false,
  samplesAvailable: false,
  sampleFee: "free",
  samplePrice: "",
  sampleLetterRequired: false,
  sampleLetterTerms: "",
  ikpu: null,
  sampleBand: DEFAULT_SAMPLE_BAND,
  // Mirrors the backend defaults: answering an RFQ costs nothing, a contract and
  // escrow are commitments the seller opts into.
  acceptsRfq: true,
  acceptsContract: false,
  acceptsEscrow: false,
  saleMode: "from_stock",
  description: "",
  keyProperties: [],
  applications: [],
};

function stage(file: File): StagedFile {
  return {
    file,
    previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
  };
}

function release(entry: StagedFile | null | undefined): void {
  if (entry?.previewUrl) URL.revokeObjectURL(entry.previewUrl);
}

/** The warehouse string as it will be stored — the picked city, or the typed one. */
export function warehouseValue(draft: OfferDraft): string {
  return draft.warehouseChoice === OTHER_OPTION
    ? draft.warehouseOther.trim()
    : draft.warehouseChoice;
}

/** The product name as the preview sheet prints it. */
export function productNameOf(draft: OfferDraft, catalogLabel: string | null): string {
  if (draft.productChoice === PRODUCT_OTHER) return draft.productText.trim();
  return catalogLabel ?? "";
}

/**
 * Turn the draft into the API payload.
 *
 * The two «Другое» escapes are resolved here rather than at each call site:
 * `product_id` and `product_text` are mutually exclusive on the server, and a
 * payload carrying both is the classic way an offer ends up named twice.
 */
export function draftToPayload(draft: OfferDraft): OfferPayload {
  const isOther = draft.productChoice === PRODUCT_OTHER;
  const onOrder = draft.availability === "on_order";
  const trim = (value: string): string | null => (value.trim() === "" ? null : value.trim());

  return {
    product_id: isOther || draft.productChoice === "" ? null : Number(draft.productChoice),
    product_text: isOther ? trim(draft.productText) : null,
    grade_text: trim(draft.gradeText),
    polymer_type: trim(draft.category),
    manufacturer: trim(draft.manufacturer),
    key_properties: draft.keyProperties,
    applications: draft.applications,
    availability: draft.availability,
    // «Под заказ» has no stock on hand and no unit price — the card says
    // "по запросу", and sending a leftover figure would contradict it.
    qty_available: onOrder ? null : trim(draft.qty),
    qty_unit: draft.qtyUnit,
    price: onOrder ? null : trim(draft.price),
    currency: draft.currency,
    incoterms: draft.incoterms,
    warehouse_city: trim(warehouseValue(draft)),
    country: trim(draft.originCountry),
    min_order_qty: trim(draft.minOrderQty),
    description: trim(draft.description),
    lead_time_days: DISPATCH_BANDS.find((b) => b.id === draft.dispatchBand)?.days ?? null,
    sale_mode: draft.saleMode === "" ? null : (draft.saleMode as SaleMode),
    accepts_rfq: draft.acceptsRfq,
    accepts_contract: draft.acceptsContract,
    accepts_escrow: draft.acceptsEscrow,
    substance_id: draft.substance?.id ?? null,
    cas_number: trim(draft.casNumber),
    hs_code: trim(draft.hsCode),
    declared_concentration_pct: trim(draft.concentration),
    samples_available: draft.samplesAvailable,
    // Only meaningful with samples on: a letter gating a sample nobody offers
    // would be a rule with nothing to apply to.
    sample_letter_required: draft.samplesAvailable && draft.sampleLetterRequired,
    sample_letter_terms:
      draft.samplesAvailable && draft.sampleLetterRequired ? trim(draft.sampleLetterTerms) : null,
    // The API rejects sample terms without samples, and a free sample is a NULL
    // price — not a zero, which would print as "0 USD" on the card.
    sample_price:
      draft.samplesAvailable && draft.sampleFee === "paid" ? trim(draft.samplePrice) : null,
    sample_dispatch_days: draft.samplesAvailable
      ? (SAMPLE_BANDS.find((b) => b.id === draft.sampleBand)?.days ?? null)
      : null,
    // All five or none: a half-filled ИКПУ builds a document Didox rejects at
    // SEND time, after the seller has already typed their key password.
    ikpu_code: draft.ikpu?.code ?? null,
    ikpu_name: draft.ikpu?.name ?? null,
    ikpu_package_code: draft.ikpu?.packageCode ?? null,
    ikpu_package_name: draft.ikpu?.packageName ?? null,
    ikpu_origin: draft.ikpu?.origin ?? null,
  };
}

export const useOfferDraft = create<DraftState>((set, get) => ({
  draft: { ...EMPTY_DRAFT },
  offerId: null,
  photos: [],
  documents: {},
  labPassport: null,
  serverFiles: [],
  removedFileIds: [],

  setField: (key, value) => set((s) => ({ draft: { ...s.draft, [key]: value } })),
  patch: (patch) => set((s) => ({ draft: { ...s.draft, ...patch } })),

  addPhotos: (files) => set((s) => ({ photos: [...s.photos, ...files.map(stage)] })),
  removePhoto: (index) =>
    set((s) => {
      release(s.photos[index]);
      return { photos: s.photos.filter((_, i) => i !== index) };
    }),

  setDocument: (kind, file) =>
    set((s) => {
      release(s.documents[kind]);
      const next = { ...s.documents };
      if (file) next[kind] = stage(file);
      else delete next[kind];
      return { documents: next };
    }),

  setLabPassport: (file) =>
    set((s) => {
      release(s.labPassport);
      return { labPassport: file ? stage(file) : null };
    }),

  removeServerFile: (fileId) =>
    set((s) => ({
      serverFiles: s.serverFiles.filter((f) => f.id !== fileId),
      removedFileIds: [...s.removedFileIds, fileId],
    })),

  hydrate: (offer) => {
    const warehouse = offer.warehouse_city ?? "";
    const known = (WAREHOUSE_LOCATIONS as readonly string[]).includes(warehouse);
    set({
      offerId: offer.id,
      photos: [],
      documents: {},
      labPassport: null,
      serverFiles: offer.files,
      removedFileIds: [],
      draft: {
        ...EMPTY_DRAFT,
        productChoice:
          offer.product_id != null
            ? String(offer.product_id)
            : offer.product_text
              ? PRODUCT_OTHER
              : "",
        productText: offer.product_text ?? "",
        gradeText: offer.grade_text ?? "",
        casNumber: offer.cas_number ?? "",
        hsCode: offer.hs_code ?? "",
        manufacturer: offer.manufacturer ?? "",
        originCountry: offer.country ?? DEFAULT_ORIGIN_COUNTRY,
        category: offer.polymer_type ?? "",
        substance: offer.substance ?? null,
        concentration:
          offer.declared_concentration_pct != null
            ? String(offer.declared_concentration_pct)
            : "",
        availability: offer.availability,
        qty: offer.qty_available != null ? String(offer.qty_available) : "",
        qtyUnit: offer.qty_unit,
        price: offer.price != null ? String(offer.price) : "",
        currency: offer.currency,
        incoterms: offer.incoterms,
        minOrderQty: offer.min_order_qty != null ? String(offer.min_order_qty) : "",
        warehouseChoice: warehouse === "" ? WAREHOUSE_LOCATIONS[0] : known ? warehouse : OTHER_OPTION,
        warehouseOther: known ? "" : warehouse,
        dispatchBand: bandForDays(DISPATCH_BANDS, offer.lead_time_days ?? null, DEFAULT_DISPATCH_BAND),
        hasPassport: offer.has_lab_passport ?? false,
        samplesAvailable: offer.samples_available ?? false,
        sampleLetterRequired: offer.sample_letter_required ?? false,
        sampleLetterTerms: offer.sample_letter_terms ?? "",
        ikpu: offer.ikpu_code
          ? {
              code: offer.ikpu_code,
              name: offer.ikpu_name ?? offer.ikpu_code,
              packageCode: offer.ikpu_package_code ?? "",
              packageName: offer.ikpu_package_name ?? "",
              origin: offer.ikpu_origin ?? null,
            }
          : null,
        sampleFee: offer.sample_price != null ? "paid" : "free",
        samplePrice: offer.sample_price != null ? String(offer.sample_price) : "",
        sampleBand: bandForDays(SAMPLE_BANDS, offer.sample_dispatch_days ?? null, DEFAULT_SAMPLE_BAND),
        acceptsRfq: offer.accepts_rfq,
        acceptsContract: offer.accepts_contract,
        acceptsEscrow: offer.accepts_escrow,
        saleMode: offer.sale_mode ?? "",
        description: offer.description ?? "",
        keyProperties: offer.key_properties ?? [],
        applications: offer.applications ?? [],
      },
    });
  },

  reset: () => {
    const { photos, documents, labPassport } = get();
    photos.forEach(release);
    Object.values(documents).forEach(release);
    release(labPassport);
    set({
      draft: { ...EMPTY_DRAFT },
      offerId: null,
      photos: [],
      documents: {},
      labPassport: null,
      serverFiles: [],
      removedFileIds: [],
    });
  },
}));
