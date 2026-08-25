import { useCallback, useState } from "react";

import { ApiError } from "@/shared/api";
import { CapiwsError, getEimzoBridge } from "@/shared/lib/eimzo";
import type { EimzoCertificate, EimzoSignature } from "@/shared/lib/eimzo";

/**
 * State machine for one E-IMZO signing attempt (TA2.1):
 *   probing → module_missing | (listing → no_certs | selecting | signing) →
 *   verifying → success | error.
 *
 * API-agnostic: the caller supplies a `signer` (getChallenge + verify), so the
 * same CAPIWS flow drives both company-identity confirmation and contract signing.
 */
export type EimzoState =
  | "idle"
  | "probing"
  | "module_missing"
  | "listing"
  | "no_certs"
  | "selecting"
  | "signing"
  | "verifying"
  | "success"
  | "error";

/** Stable error codes → i18n keys under `eimzo.errors.*`. */
export type EimzoErrorCode =
  | "unavailable"
  | "module_not_authorized"
  | "mismatch"
  | "expired"
  | "already_registered"
  | "signature_invalid"
  | "cert_revoked"
  | "cert_no_tin"
  | "sign_failed"
  | "unknown";

/**
 * The chosen certificate's subject carries no organisation STIR, so there is
 * nothing to register the company under.
 *
 * Declared here rather than beside the signer that raises it: `mapError` has to
 * recognise it, and importing the signer module from the state machine would
 * close an import cycle (the signers import this module for `EimzoSigner`).
 */
export class CertificateHasNoTin extends Error {}

export interface EimzoVerifyOutcome<T> {
  ok: boolean;
  reason: string | null;
  data: T;
}

export interface EimzoSigner<T> {
  /**
   * Issue the challenge to sign (server round-trip).
   *
   * Receives the chosen certificate because a challenge is company-scoped and a
   * first-time registration has no company yet — the wizard's signer reads the
   * STIR out of the certificate subject and creates the row here. Signers that
   * already know their subject (verification status, contracts) ignore it.
   */
  getChallenge: (cert: EimzoCertificate) => Promise<string>;
  /**
   * Submit the signature and return the typed outcome.
   *
   * Receives BOTH halves rather than the PKCS#7 alone. Our own sidecar only needs
   * `pkcs7_64` and those signers destructure it, but Didox's timestamp endpoint
   * requires `signature_hex` too — and a bridge that had already thrown it away
   * left no way to add that later without changing every signer anyway.
   */
  verify: (signature: EimzoSignature) => Promise<EimzoVerifyOutcome<T>>;
}

interface UseEimzoSignArgs<T> {
  signer: EimzoSigner<T>;
  onConfirmed?: (data: T) => void;
}

interface UseEimzoSign<T> {
  state: EimzoState;
  certs: EimzoCertificate[];
  error: EimzoErrorCode | null;
  result: T | null;
  start: () => Promise<void>;
  pick: (certId: string) => Promise<void>;
  reset: () => void;
}

function mapError(err: unknown): EimzoErrorCode {
  if (err instanceof CertificateHasNoTin) return "cert_no_tin";
  // The module is running and refused this Origin — an operator problem (the domain
  // needs a key issued by E-IMZO), not something the user can retry their way out of.
  if (err instanceof CapiwsError) {
    return err.isApiKeyRejection ? "module_not_authorized" : "sign_failed";
  }
  if (err instanceof ApiError) {
    if (err.status === 422) return "mismatch";
    if (err.status === 400) return "expired";
    if (err.status === 409) return "already_registered";
    if (err.status === 503) return "unavailable";
    return "unknown";
  }
  if (err instanceof Error && err.message.startsWith("eimzo_")) return "sign_failed";
  return "unknown";
}

function mapResultReason(reason: string | null): EimzoErrorCode {
  if (reason === "cert_revoked") return "cert_revoked";
  if (reason === "challenge_mismatch") return "mismatch";
  return "signature_invalid";
}

export function useEimzoSign<T>({ signer, onConfirmed }: UseEimzoSignArgs<T>): UseEimzoSign<T> {
  const [state, setState] = useState<EimzoState>("idle");
  const [certs, setCerts] = useState<EimzoCertificate[]>([]);
  const [error, setError] = useState<EimzoErrorCode | null>(null);
  const [result, setResult] = useState<T | null>(null);

  const reset = useCallback(() => {
    setState("idle");
    setCerts([]);
    setError(null);
    setResult(null);
  }, []);

  const runVerify = useCallback(
    async (cert: EimzoCertificate) => {
      const bridge = getEimzoBridge();
      try {
        setState("signing");
        const challenge = await signer.getChallenge(cert);
        const signature = await bridge.sign(cert.id, challenge);
        setState("verifying");
        const out = await signer.verify(signature);
        if (!out.ok) {
          setError(mapResultReason(out.reason));
          setState("error");
          return;
        }
        setResult(out.data);
        setState("success");
        onConfirmed?.(out.data);
      } catch (err) {
        setError(mapError(err));
        setState("error");
      }
    },
    [signer, onConfirmed],
  );

  const start = useCallback(async () => {
    setError(null);
    setResult(null);
    const bridge = getEimzoBridge();
    setState("probing");
    let available = false;
    try {
      available = await bridge.probe();
    } catch {
      available = false;
    }
    if (!available) {
      setState("module_missing");
      return;
    }
    setState("listing");
    let list: EimzoCertificate[] = [];
    try {
      list = await bridge.listCertificates();
    } catch (err) {
      setError(mapError(err));
      setState("error");
      return;
    }
    if (list.length === 0) {
      setState("no_certs");
      return;
    }
    setCerts(list);
    const [only] = list;
    if (list.length === 1 && only) {
      // Pass the object, not the id: `certs` state is not readable yet in this
      // tick, and the signer needs the subject to resolve its company.
      await runVerify(only);
      return;
    }
    setState("selecting");
  }, [runVerify]);

  const pick = useCallback(
    async (certId: string) => {
      const cert = certs.find((c) => c.id === certId);
      if (!cert) return;
      await runVerify(cert);
    },
    [certs, runVerify],
  );

  return { state, certs, error, result, start, pick, reset };
}
