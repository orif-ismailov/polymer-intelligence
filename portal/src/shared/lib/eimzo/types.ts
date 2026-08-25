/**
 * E-IMZO browser-bridge contract (R3 Stage A — TA2.1).
 *
 * The signing feature depends only on this small interface, never on the raw
 * CAPIWS WebSocket protocol. The real implementation (`CapiwsBridge`) wraps the
 * local E-IMZO module; tests and the desktop-less preview inject a stub bridge on
 * `window.__EIMZO_BRIDGE__`, so the whole flow is exercised without a device.
 */

export interface EimzoCertificate {
  /** Opaque handle passed back to `sign()` (encodes disk/path/name/alias). */
  id: string;
  /** Display string — organisation + holder (from the certificate subject). */
  subjectName: string;
  /** Organisation INN/STIR (OID 1.2.860.3.16.1.1) — what company.tax_id is matched against. */
  tin?: string;
  /** Holder full name (CN), when present. */
  name?: string;
  /** Organisation name (O), when present. */
  org?: string;
  /** Holder PINFL (OID 1.2.860.3.16.1.2). Never render unmasked. */
  pinfl?: string;
  /** Holder personal INN (UID) — distinct from `tin`, which is the ORGANISATION's. */
  personalInn?: string;
  /** Holder position/title (T), when present. */
  position?: string;
  /** Certificate serial, when present. */
  serialNumber?: string;
  /** Certificate validity end, for display. Format is the module's, not ISO. */
  validTo?: string;
}

/**
 * What `pkcs7.create_pkcs7` actually returns — BOTH halves.
 *
 * `signature_hex` is the raw signature value (128 hex chars for GOST) that sits
 * inside the PKCS#7. Our own backend only ever needed `pkcs7_64`, so the bridge
 * used to return that string alone and drop the rest on the floor — which made
 * Didox impossible, because `POST /v1/dsvs/timestamp` requires both and rejects a
 * bare PKCS#7. The module was always sending it; nothing was reading it.
 */
export interface EimzoSignature {
  pkcs7_64: string;
  signature_hex: string;
}

/**
 * A loaded key, held open across several signatures.
 *
 * `load_key` is what opens the native password dialog, so a flow that signs twice
 * (Didox: once over the INN to mint a session, once over the document) would
 * otherwise prompt twice for the same key. Opening a session once and signing
 * repeatedly is the difference between one dialog and N.
 */
export interface EimzoKeySession {
  /** Sign TEXT — it is base64-encoded for you. */
  sign(challenge: string): Promise<EimzoSignature>;
  /**
   * Sign data that is ALREADY base64.
   *
   * Not a convenience: Didox hands us the payload pre-encoded, and decoding it
   * just to let `sign()` re-encode is lossy. `atob()` yields a latin-1 string of
   * the UTF-8 bytes, which `encodeURIComponent` then encodes AGAIN — so
   * «Поставка» is signed as «ÐÐ¾ÑÑÐ°Ð²ÐºÐ°» and the signature covers bytes the
   * verifier will never reproduce. Silent, and only visible once a real document
   * with Cyrillic in it goes through.
   */
  signBase64(dataB64: string): Promise<EimzoSignature>;
  /** Best-effort — a failed unload must never fail a completed signature. */
  close(): Promise<void>;
}

export interface EimzoBridge {
  /** True when the local E-IMZO module is reachable. */
  probe(): Promise<boolean>;
  /** Enumerate the user's available certificates. */
  listCertificates(): Promise<EimzoCertificate[]>;
  /** Sign TEXT once: load the key, sign, unload. One native password prompt. */
  sign(certId: string, challenge: string): Promise<EimzoSignature>;
  /**
   * Sign ALREADY-base64 data once. Use this for anything the server handed us
   * pre-encoded — see `EimzoKeySession.signBase64` for why round-tripping
   * through `atob` corrupts non-ASCII.
   */
  signBase64?(certId: string, dataB64: string): Promise<EimzoSignature>;
  /**
   * Hold a key open for several signatures. Optional: an injected stub bridge
   * need not implement it, and callers fall back to `sign()` per signature —
   * correct, just one prompt each.
   */
  openSession?(certId: string): Promise<EimzoKeySession>;
}
