import { useState } from "react";

import {
  manufacturerApi,
  useCreateFactoryRfq,
  type FactoryRfq,
  type FactoryRfqDocumentKind,
} from "@/entities/manufacturer";

import { useFactoryRfqDraft } from "./draftStore";

/**
 * Create the RFQ, then upload whichever document slots the buyer filled in.
 *
 * Two calls, not one multipart POST: the RFQ row has to exist before a document
 * can attach to it (`factory_rfq_documents.factory_rfq_id` is a real FK), and a
 * partial-document failure must not lose the RFQ itself — the buyer keeps the
 * created number even if a single upload fails.
 */
export function useSubmitFactoryRfq(manufacturerId: number) {
  const create = useCreateFactoryRfq(manufacturerId);
  const toPayload = useFactoryRfqDraft((s) => s.toPayload);
  const [error, setError] = useState<Error | null>(null);
  const [uploading, setUploading] = useState(false);

  async function submit(companyId: number, offerId: number): Promise<FactoryRfq | null> {
    setError(null);
    try {
      const payload = toPayload(companyId, offerId);
      const rfq = await create.mutateAsync(payload);

      const documents = useFactoryRfqDraft.getState().draft.documents;
      const entries = Object.entries(documents) as [FactoryRfqDocumentKind, File | undefined][];
      if (entries.length > 0) {
        setUploading(true);
        for (const [kind, file] of entries) {
          if (!file) continue;
          // Sequential, not Promise.all: a failed upload should not race the
          // others into an unclear half-done state on screen.
          await manufacturerApi.uploadRfqDocument(rfq.id, companyId, kind, file);
        }
      }
      return rfq;
    } catch (err) {
      const e = err instanceof Error ? err : new Error(String(err));
      setError(e);
      return null;
    } finally {
      setUploading(false);
    }
  }

  return {
    submit,
    error,
    isPending: create.isPending || uploading,
  };
}
