import { create } from "zustand";

import { PRODUCT_OTHER } from "@/entities/product";
import type { RequestPayload } from "@/entities/request";

import {
  DEFAULT_DELIVERY_BAND,
  DEFAULT_DEST_COUNTRY,
  DEFAULT_VALIDITY_DAYS,
  DELIVERY_BANDS,
  OTHER_OPTION,
  type DeliveryBandId,
  type OfferChannel,
  type RequestDocKind,
  type VisibilityOption,
} from "./constants";

export interface RequestDraft {
  // ── 1. Продукт ────────────────────────────────────────────────────────────
  /** Stringified product id, `"other"`, or "". */
  productChoice: string;
  /** Free-typed name while `productChoice === "other"`. */
  productText: string;
  gradeText: string;
  /** Catalog product code (PP / HDPE) — satisfies grade-OR-polymer on submit. */
  polymerType: string;
  /** Display name of the chosen catalog row, for the preview sheet. */
  productLabel: string;
  /** Polymer family filter on sheet 1 — display label, not stored. */
  categoryFilter: string;
  searchQuery: string;
  // ── 2. Параметры ──────────────────────────────────────────────────────────
  volume: string;
  volumeUnit: string;
  targetPrice: string;
  currency: string;
  incoterms: string;
  destinationCountry: string;
  /** A `DEST_CITIES` member, or `"other"`. */
  cityChoice: string;
  cityOther: string;
  deliveryBand: DeliveryBandId;
  validityDays: number;
  // ── 3. Дополнительно ──────────────────────────────────────────────────────
  specs: string;
  requiredDocs: RequestDocKind[];
  comment: string;
  // ── 4. Условия общения ────────────────────────────────────────────────────
  offerChannel: OfferChannel;
  visibility: VisibilityOption;
}

interface DraftState {
  draft: RequestDraft;
  companyName: string;
  setField: <K extends keyof RequestDraft>(key: K, value: RequestDraft[K]) => void;
  patch: (patch: Partial<RequestDraft>) => void;
  toggleDoc: (kind: RequestDocKind) => void;
  /** Seed company-scoped defaults when the flow opens. */
  begin: (companyName: string) => void;
  reset: () => void;
  /** Build the POST body. Specs/docs/channel fold into `comment`. */
  toPayload: (companyId: number) => RequestPayload;
}

const EMPTY: RequestDraft = {
  productChoice: "",
  productText: "",
  gradeText: "",
  polymerType: "",
  productLabel: "",
  categoryFilter: "",
  searchQuery: "",
  volume: "",
  volumeUnit: "MT",
  targetPrice: "",
  currency: "USD",
  incoterms: "CIF",
  destinationCountry: DEFAULT_DEST_COUNTRY,
  cityChoice: "Ташкент",
  cityOther: "",
  deliveryBand: DEFAULT_DELIVERY_BAND,
  validityDays: DEFAULT_VALIDITY_DAYS,
  specs: "",
  requiredDocs: [],
  comment: "",
  offerChannel: "app",
  visibility: "verified",
};

function cityValue(draft: RequestDraft): string {
  if (draft.cityChoice === OTHER_OPTION) return draft.cityOther.trim();
  return draft.cityChoice.trim();
}

function desiredDateFor(band: DeliveryBandId): string {
  const days = DELIVERY_BANDS.find((b) => b.id === band)?.days ?? 30;
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function urgencyFor(band: DeliveryBandId): string {
  return DELIVERY_BANDS.find((b) => b.id === band)?.urgency ?? "medium";
}

/**
 * Fold the mockup-only fields into the single `comment` column the API accepts,
 * so staff still see specs / required docs / channel preferences without a
 * migration. Blank sections are omitted rather than printed as empty headers.
 */
function buildComment(draft: RequestDraft, tDocs: (kind: RequestDocKind) => string): string {
  const parts: string[] = [];
  const specs = draft.specs.trim();
  if (specs) parts.push(specs);

  if (draft.requiredDocs.length > 0) {
    parts.push(`Требуемые документы: ${draft.requiredDocs.map(tDocs).join(", ")}`);
  }

  const extra = draft.comment.trim();
  if (extra) parts.push(extra);

  // Channel + visibility are soft preferences — keep them short.
  const prefs: string[] = [];
  if (draft.offerChannel !== "app") prefs.push(`канал: ${draft.offerChannel}`);
  if (draft.visibility !== "verified") prefs.push(`видимость: ${draft.visibility}`);
  if (prefs.length) parts.push(`Предпочтения: ${prefs.join("; ")}`);

  return parts.join("\n\n") || "";
}

export const useRequestDraft = create<DraftState>((set, get) => ({
  draft: { ...EMPTY },
  companyName: "",

  setField: (key, value) =>
    set((s) => ({ draft: { ...s.draft, [key]: value } })),

  patch: (patch) => set((s) => ({ draft: { ...s.draft, ...patch } })),

  toggleDoc: (kind) =>
    set((s) => {
      const has = s.draft.requiredDocs.includes(kind);
      return {
        draft: {
          ...s.draft,
          requiredDocs: has
            ? s.draft.requiredDocs.filter((k) => k !== kind)
            : [...s.draft.requiredDocs, kind],
        },
      };
    }),

  begin: (companyName) =>
    set({ draft: { ...EMPTY }, companyName }),

  reset: () => set({ draft: { ...EMPTY }, companyName: "" }),

  toPayload: (companyId) => {
    const { draft, companyName } = get();
    const isOther = draft.productChoice === PRODUCT_OTHER;
    const productId =
      !isOther && draft.productChoice !== "" ? Number(draft.productChoice) : null;

    // Doc labels stay Russian in the folded comment — staff UI is RU-primary
    // and a translated fold would need i18n at submit time.
    const docLabel = (kind: RequestDocKind): string => {
      const map: Record<RequestDocKind, string> = {
        sds: "SDS",
        coa: "COA",
        coo: "Сертификат происхождения",
        commercial: "Коммерческое предложение",
        other: "Другие документы",
      };
      return map[kind];
    };

    const comment = buildComment(draft, docLabel);

    return {
      company_id: companyId,
      product_id: productId,
      product_text: isOther ? draft.productText.trim() || null : null,
      grade_text: draft.gradeText.trim() || null,
      polymer_type:
        draft.polymerType.trim() ||
        (isOther ? null : draft.productLabel.trim() || null),
      volume: draft.volume,
      volume_unit: draft.volumeUnit,
      target_price: draft.targetPrice.trim() || null,
      currency: draft.currency,
      incoterms: draft.incoterms,
      destination_country: draft.destinationCountry.trim().toUpperCase() || "UZ",
      port_or_city: cityValue(draft) || null,
      desired_date: desiredDateFor(draft.deliveryBand),
      validity_days: draft.validityDays,
      urgency: urgencyFor(draft.deliveryBand),
      comment: comment || null,
      company_name: companyName || null,
    };
  },
}));

/** Resolved city string for the preview sheet. */
export function resolvedCity(draft: RequestDraft): string {
  return cityValue(draft);
}
