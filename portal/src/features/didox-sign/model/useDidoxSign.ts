import { useCallback, useState } from "react";

import { didoxApi } from "@/entities/edi";
import type { DidoxDocumentResult } from "@/entities/edi";
import { useDidoxSession } from "@/features/didox-session";
import { ApiError } from "@/shared/api";
import { CapiwsError, getEimzoBridge } from "@/shared/lib/eimzo";

/**
 * Sign a Didox document — the two-round-trip exchange (P7.a W11).
 *
 * Round 1 asks the server what to sign; round 2 sends the signature. It cannot
 * be one call: the bytes are the JSON **Didox** holds for the document, so the
 * browser cannot derive them, and re-deriving them on submit could produce
 * something different from what the user actually signed.
 *
 * Two things here are easy to get wrong and are therefore not left to callers:
 *
 *   * `signBase64` — NOT `sign`. The payload arrives already base64; decoding it
 *     to hand to `sign()` corrupts every non-ASCII character, because `atob`
 *     yields latin-1 bytes that then get UTF-8 encoded a second time. Cyrillic
 *     goes in as «Поставка» and is signed as «ÐÐ¾ÑÑÐ°Ð²ÐºÐ°».
 *   * the whole exchange runs inside `withSession`, so an expired 360-minute
 *     Didox session mints and retries instead of failing the click.
 */

export type DidoxSignError =
  | "module_missing"
  | "no_cert"
  | "expired"
  | "offer_required"
  | "unavailable"
  | "rejected"
  | "cancelled"
  | "failed";

interface UseDidoxSign {
  signing: boolean;
  error: DidoxSignError | null;
  /**
   * What Didox actually said, when they said anything.
   *
   * Their 422 carries the only actionable sentence in the whole exchange — «ИНН/
   * ПИНФЛ заказчика некорректный. ИНН/ПИНФЛ: 562353400» names the problem and the
   * company it is about. Collapsing that into «не удалось подписать документ»
   * cost an afternoon of guessing on 25.08.2026, so it is carried out of the
   * hook and rendered verbatim.
   */
  errorMessage: string | null;
  result: DidoxDocumentResult | null;
  sign: (documentId: number) => Promise<DidoxDocumentResult | null>;
  reset: () => void;
}

/** The shape our API wraps a provider refusal in (`_provider_error`). */
interface DidoxRejection {
  error?: string;
  message?: string;
  description?: string | null;
}

export function rejectionOf(err: unknown): DidoxRejection | null {
  if (!(err instanceof ApiError)) return null;
  // `ApiError.detail` is the WHOLE response body, so FastAPI's envelope is still
  // around our object: `{ detail: { error: "didox_rejected", … } }`. Reading
  // `err.detail.error` finds nothing and silently falls back to the generic
  // «не удалось подписать» — which is the exact failure this whole change exists
  // to remove, so it is unwrapped here and pinned by a test.
  const body: unknown = err.detail;
  if (typeof body !== "object" || body === null) return null;
  const inner = (body as { detail?: unknown }).detail;
  const rejection = (typeof inner === "object" && inner !== null ? inner : body) as DidoxRejection;
  return rejection.error === "didox_rejected" ? rejection : null;
}

export function useDidoxSign(companyId: number, taxId: string): UseDidoxSign {
  const { withSession } = useDidoxSession(companyId, taxId);
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState<DidoxSignError | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<DidoxDocumentResult | null>(null);

  const reset = useCallback(() => {
    setError(null);
    setErrorMessage(null);
    setResult(null);
  }, []);

  const sign = useCallback(
    async (documentId: number): Promise<DidoxDocumentResult | null> => {
      setSigning(true);
      setError(null);
      setErrorMessage(null);
      try {
        const bridge = getEimzoBridge();
        if (!(await bridge.probe())) throw new Error("eimzo_module_missing");
        const certs = await bridge.listCertificates();
        const cert = certs.find((c) => c.tin === taxId) ?? certs[0];
        if (!cert) throw new Error("eimzo_no_cert");

        const out = await withSession(async () => {
          const { data_b64 } = await didoxApi.signPayload(documentId);
          // Pre-encoded — hand it through untouched.
          const signature = await bridge.signBase64!(cert.id, data_b64);
          return didoxApi.signDocument(documentId, signature);
        });

        setResult(out);
        return out;
      } catch (err) {
        if (err instanceof CapiwsError && err.isCancelled) setError("cancelled");
        else if (err instanceof Error && err.message === "eimzo_module_missing") setError("module_missing");
        else if (err instanceof Error && err.message === "eimzo_no_cert") setError("no_cert");
        else if (err instanceof ApiError && err.status === 400) setError("expired");
        else if (err instanceof ApiError && err.status === 503) setError("unavailable");
        else if (
          err instanceof ApiError &&
          err.status === 409 &&
          err.detail === "didox_offer_required"
        ) {
          setError("offer_required");
        } else {
          // Their words if they gave any, ours only as a last resort. Their
          // `description` (what to DO) wins over `message` (what went wrong).
          const rejection = rejectionOf(err);
          if (rejection) {
            setError("rejected");
            setErrorMessage(rejection.description || rejection.message || null);
          } else setError("failed");
        }
        return null;
      } finally {
        setSigning(false);
      }
    },
    [taxId, withSession],
  );

  return { signing, error, errorMessage, result, sign, reset };
}
