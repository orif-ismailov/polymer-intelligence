import { useCallback, useState } from "react";

import { didoxApi } from "@/entities/edi";
import type { DidoxSignature, DidoxStatus } from "@/entities/edi";
import { ApiError } from "@/shared/api";
import { getEimzoBridge } from "@/shared/lib/eimzo";

/**
 * A Didox session — minted on demand, never as a separate ceremony.
 *
 * The wall this exists to hide: a `user-key` lasts 360 minutes and can only be
 * minted with the company's own E-IMZO key in this browser. There is no
 * server-side path. So `409 didox_session_required` is not an error to show
 * someone — it is "sign once more", and the user is already at the machine with
 * their card in the reader, because they were about to sign something anyway.
 *
 * Hence `withSession`: run an action, and if it comes back 409, mint and **retry
 * the same action**. The user sees one password dialog and their click working,
 * not a modal telling them to go and authenticate first.
 */

export type DidoxSessionError =
  | "module_missing"
  | "no_cert"
  | "cert_mismatch"
  | "disabled"
  | "failed";

interface UseDidoxSession {
  minting: boolean;
  error: DidoxSessionError | null;
  /** Mint explicitly (the onboarding card's button). */
  open: () => Promise<DidoxStatus | null>;
  /** Run `action`; on `409 didox_session_required`, mint and run it once more. */
  withSession: <T>(action: () => Promise<T>) => Promise<T>;
  reset: () => void;
}

/** The Didox session is proven by signing the company's own ИНН. */
async function signTin(taxId: string): Promise<DidoxSignature> {
  const bridge = getEimzoBridge();
  if (!(await bridge.probe())) throw new Error("eimzo_module_missing");

  const certs = await bridge.listCertificates();
  if (certs.length === 0) throw new Error("eimzo_no_cert");
  // The certificate must belong to THIS company: Didox mints the key against the
  // ИНН in the subject, so a mismatch would silently act as someone else.
  const cert = certs.find((c) => c.tin === taxId);
  if (!cert) throw new Error("eimzo_cert_mismatch");

  return bridge.sign(cert.id, taxId);
}

export function useDidoxSession(companyId: number, taxId: string): UseDidoxSession {
  const [minting, setMinting] = useState(false);
  const [error, setError] = useState<DidoxSessionError | null>(null);

  const reset = useCallback(() => setError(null), []);

  const open = useCallback(async (): Promise<DidoxStatus | null> => {
    setMinting(true);
    setError(null);
    try {
      return await didoxApi.openSession(companyId, await signTin(taxId));
    } catch (err) {
      if (err instanceof Error && err.message === "eimzo_module_missing") setError("module_missing");
      else if (err instanceof Error && err.message === "eimzo_no_cert") setError("no_cert");
      else if (err instanceof Error && err.message === "eimzo_cert_mismatch") setError("cert_mismatch");
      else if (err instanceof ApiError && err.status === 409) setError("disabled");
      else setError("failed");
      return null;
    } finally {
      setMinting(false);
    }
  }, [companyId, taxId]);

  const withSession = useCallback(
    async <T,>(action: () => Promise<T>): Promise<T> => {
      try {
        return await action();
      } catch (err) {
        const needsSession =
          err instanceof ApiError &&
          err.status === 409 &&
          typeof err.detail === "string" &&
          err.detail === "didox_session_required";
        if (!needsSession) throw err;

        setMinting(true);
        try {
          await didoxApi.openSession(companyId, await signTin(taxId));
        } finally {
          setMinting(false);
        }
        // Retry ONCE. A second 409 is a real problem (the key minted a session
        // for a different company, say) and must surface rather than loop.
        return action();
      }
    },
    [companyId, taxId],
  );

  return { minting, error, open, withSession, reset };
}
