import { useCallback, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { didoxApi, didoxStatusKey } from "@/entities/edi";
import { getEimzoBridge } from "@/shared/lib/eimzo";

import { useDidoxSession } from "./useDidoxSession";

export type DidoxOfferError = "module_missing" | "cert_mismatch" | "failed";

interface UseDidoxOffer {
  signing: boolean;
  error: DidoxOfferError | null;
  /** Sign Didox's public offer; true once Didox has accepted it. */
  sign: () => Promise<boolean>;
}

/**
 * Sign Didox's public offer — the one-time step that unblocks every send.
 *
 * The bytes come from the server (it does the two round trips their docs
 * describe) and arrive ALREADY base64, so they go through `signBase64`:
 * decoding just to let `sign()` re-encode corrupts every non-ASCII character,
 * and this document is full of them.
 */
export function useDidoxOffer(companyId: number, taxId: string): UseDidoxOffer {
  const queryClient = useQueryClient();
  const { withSession } = useDidoxSession(companyId, taxId);
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState<DidoxOfferError | null>(null);

  const sign = useCallback(async (): Promise<boolean> => {
    setSigning(true);
    setError(null);
    try {
      const bridge = getEimzoBridge();
      if (!(await bridge.probe())) throw new Error("module_missing");
      const certs = await bridge.listCertificates();
      const cert = certs.find((c) => c.tin === taxId);
      if (!cert) throw new Error("cert_mismatch");

      const dataB64 = await withSession(() => didoxApi.offerToSign(companyId));
      const signature = bridge.signBase64
        ? await bridge.signBase64(cert.id, dataB64)
        : await bridge.sign(cert.id, dataB64);
      await withSession(() => didoxApi.acceptOffer(companyId, signature));
      await queryClient.invalidateQueries({
        queryKey: didoxStatusKey(companyId),
      });
      return true;
    } catch (err) {
      const code = err instanceof Error ? err.message : "";
      setError(
        code === "module_missing" || code === "cert_mismatch" ? code : "failed",
      );
      return false;
    } finally {
      setSigning(false);
    }
  }, [companyId, taxId, withSession, queryClient]);

  return { signing, error, sign };
}
