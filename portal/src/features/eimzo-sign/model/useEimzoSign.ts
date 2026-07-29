import { useCallback, useState } from "react";

import { ApiError } from "@/shared/api";
import { getEimzoBridge } from "@/shared/lib/eimzo";
import type { EimzoCertificate } from "@/shared/lib/eimzo";

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
  | "mismatch"
  | "expired"
  | "already_registered"
  | "signature_invalid"
  | "cert_revoked"
  | "sign_failed"
  | "unknown";

export interface EimzoVerifyOutcome<T> {
  ok: boolean;
  reason: string | null;
  data: T;
}

export interface EimzoSigner<T> {
  /** Issue the challenge to sign (server round-trip). */
  getChallenge: () => Promise<string>;
  /** Submit the PKCS#7 and return the typed outcome. */
  verify: (pkcs7: string) => Promise<EimzoVerifyOutcome<T>>;
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
    async (certId: string) => {
      const bridge = getEimzoBridge();
      try {
        setState("signing");
        const challenge = await signer.getChallenge();
        const pkcs7 = await bridge.sign(certId, challenge);
        setState("verifying");
        const out = await signer.verify(pkcs7);
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
      await runVerify(only.id);
      return;
    }
    setState("selecting");
  }, [runVerify]);

  const pick = useCallback(
    async (certId: string) => {
      await runVerify(certId);
    },
    [runVerify],
  );

  return { state, certs, error, result, start, pick, reset };
}
