import { useCallback, useRef, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { verificationKeys } from "@/entities/verification";
import { companyKeys } from "@/entities/company";
import { ApiError } from "@/shared/api";
import { getEimzoBridge } from "@/shared/lib/eimzo";
import type { EimzoCertificate } from "@/shared/lib/eimzo";

import { eimzoApi } from "./api";
import type { EimzoVerifyOut } from "./api";

/**
 * State machine for one E-IMZO signing attempt (TA2.1):
 *   probing → module_missing | (listing → no_certs | selecting | signing) →
 *   verifying → success | error.
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

interface UseEimzoSignArgs {
  onConfirmed?: (result: EimzoVerifyOut) => void;
}

interface UseEimzoSign {
  state: EimzoState;
  certs: EimzoCertificate[];
  error: EimzoErrorCode | null;
  result: EimzoVerifyOut | null;
  start: (companyId: number) => Promise<void>;
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

export function useEimzoSign({ onConfirmed }: UseEimzoSignArgs = {}): UseEimzoSign {
  const qc = useQueryClient();
  const [state, setState] = useState<EimzoState>("idle");
  const [certs, setCerts] = useState<EimzoCertificate[]>([]);
  const [error, setError] = useState<EimzoErrorCode | null>(null);
  const [result, setResult] = useState<EimzoVerifyOut | null>(null);
  const companyIdRef = useRef<number | null>(null);

  const reset = useCallback(() => {
    setState("idle");
    setCerts([]);
    setError(null);
    setResult(null);
    companyIdRef.current = null;
  }, []);

  const runVerify = useCallback(
    async (companyId: number, certId: string) => {
      const bridge = getEimzoBridge();
      try {
        setState("signing");
        const { challenge } = await eimzoApi.challenge(companyId);
        const pkcs7 = await bridge.sign(certId, challenge);
        setState("verifying");
        const out = await eimzoApi.verify(companyId, pkcs7);
        if (!out.ok) {
          setError(mapResultReason(out.reason));
          setResult(out);
          setState("error");
          return;
        }
        setResult(out);
        setState("success");
        await qc.invalidateQueries({ queryKey: companyKeys.detail(companyId) });
        qc.setQueryData(verificationKeys.detail(companyId), out.case);
        onConfirmed?.(out);
      } catch (err) {
        setError(mapError(err));
        setState("error");
      }
    },
    [onConfirmed, qc],
  );

  const start = useCallback(
    async (companyId: number) => {
      companyIdRef.current = companyId;
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
        await runVerify(companyId, only.id);
        return;
      }
      setState("selecting");
    },
    [runVerify],
  );

  const pick = useCallback(
    async (certId: string) => {
      const companyId = companyIdRef.current;
      if (companyId == null) return;
      await runVerify(companyId, certId);
    },
    [runVerify],
  );

  return { state, certs, error, result, start, pick, reset };
}
