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
  /** Organisation INN/STIR, when present in the subject. */
  tin?: string;
  /** Holder full name, when present. */
  name?: string;
  /** Certificate validity end (ISO), for display. */
  validTo?: string;
}

export interface EimzoBridge {
  /** True when the local E-IMZO module is reachable. */
  probe(): Promise<boolean>;
  /** Enumerate the user's available certificates. */
  listCertificates(): Promise<EimzoCertificate[]>;
  /** Produce a PKCS#7 (base64) signature over `challenge` with the chosen cert. */
  sign(certId: string, challenge: string): Promise<string>;
}
