import { api } from "@/shared/api";

/**
 * The Didox rail (P7.a W11).
 *
 * Two facts shape this whole client:
 *
 *   * **The partner token never reaches the browser.** We sign, and post
 *     `pkcs7_64` + `signature_hex` to OUR api; the server does the
 *     `/v1/dsvs/timestamp` round trip and talks to Didox.
 *   * **A Didox session lasts 360 minutes and can only be minted with the
 *     company's own E-IMZO key, in this browser.** So `409 didox_session_required`
 *     is a normal, expected answer — not an error state to show a user. The
 *     caller mints and continues.
 */

/** `disabled` is a property of the DEPLOYMENT, not of the company. */
export type DidoxState = "disabled" | "not_registered" | "offer_unsigned" | "ready";

export interface DidoxStatus {
  state: DidoxState;
  has_session: boolean;
}

export interface DidoxSignPayload {
  data_b64: string;
  /** `outgoing` — sign the stored JSON; `incoming` — the server joins with the sender's. */
  mode: "outgoing" | "incoming";
}

export interface DidoxDocumentResult {
  id: number;
  doc_type: string;
  number: string | null;
  status: number;
  didox_id: string | null;
  activated: boolean;
  archive_sha256: string | null;
  warning: Record<string, unknown> | null;
}

export interface DidoxSignature {
  pkcs7_64: string;
  signature_hex: string;
}

/** One product line as it will appear on the document. */
export interface DidoxContractLine {
  name: string;
  count: string;
  price: string;
  /** `null` means supplied WITHOUT VAT — not the same as a 0% rate. */
  vat_rate: number | null;
}

export interface DidoxContractPrefill {
  contract_id: number;
  seller_company_id: number;
  buyer_company_id: number;
  seller_name: string | null;
  buyer_name: string | null;
  /** Already created — show the document, not the form. */
  document_id: number | null;
  lines: DidoxContractLine[];
  /**
   * Why the create would fail, all of them at once: `ikpu_missing` ·
   * `signer_identity_missing:{companyId}` · `not_ready` · `wrong_rail` ·
   * `not_seller` · `party_mismatch`. Collected rather than raised one at a time
   * so the seller fixes everything in one pass instead of discovering each after
   * loading a key.
   */
  blockers: string[];
}

export const didoxApi = {
  status: (companyId: number): Promise<DidoxStatus> =>
    api.get<DidoxStatus>(`/portal/companies/${companyId}/didox/status`),

  /** Mint a session from a signature over the company's ИНН. */
  openSession: (companyId: number, signature: DidoxSignature): Promise<DidoxStatus> =>
    api.post<DidoxStatus>(`/portal/companies/${companyId}/didox/session`, signature),

  /** What the seller is about to send at the operator, and what blocks it. */
  contractPrefill: (companyId: number, contractId: number): Promise<DidoxContractPrefill> =>
    api.get<DidoxContractPrefill>(
      `/portal/companies/${companyId}/didox/contracts/${contractId}/document`,
    ),

  /**
   * Create the «Договор НК» 007 at Didox. Idempotent — a second press returns
   * the first document rather than a 409 nobody can act on.
   */
  createContractDocument: (
    companyId: number,
    contractId: number,
    lines: DidoxContractLine[] = [],
  ): Promise<DidoxDocumentResult> =>
    api.post<DidoxDocumentResult>(
      `/portal/companies/${companyId}/didox/contracts/${contractId}/document`,
      { lines },
    ),

  /**
   * The public offer, as the BYTES to sign — not the PDF.
   *
   * Didox wraps the offer PDF into a document and it is the JSON of THAT which
   * the signature must cover (their step 3). The server does both round trips and
   * hands back the base64 to sign, which is why this is a GET with a body-shaped
   * answer rather than a download.
   */
  offerToSign: (companyId: number): Promise<string> =>
    api
      .get<{ document_b64: string }>(`/portal/companies/${companyId}/didox/offer`)
      .then((r) => r.document_b64),

  /** Sign it — the one-time step that unblocks every send for this company. */
  acceptOffer: (companyId: number, signature: DidoxSignature): Promise<DidoxStatus> =>
    api.post<DidoxStatus>(`/portal/companies/${companyId}/didox/offer`, signature),

  /** Round 1 — the exact bytes to sign, stashed single-use on the server. */
  signPayload: (documentId: number): Promise<DidoxSignPayload> =>
    api.post<DidoxSignPayload>(`/portal/companies/documents/${documentId}/sign-payload`),

  /** Round 2 — timestamp, join if incoming, send. */
  signDocument: (
    documentId: number,
    signature: DidoxSignature,
  ): Promise<DidoxDocumentResult> =>
    api.post<DidoxDocumentResult>(
      `/portal/companies/documents/${documentId}/sign`,
      signature,
    ),
};

/** Didox's own status ladder, verbatim — see `didox_documents.status`. */
export const DIDOX_STATUS = {
  draft: 0,
  awaitingPartner: 1,
  awaitingUs: 2,
  signed: 3,
  rejected: 4,
  annulled: 50,
} as const;
