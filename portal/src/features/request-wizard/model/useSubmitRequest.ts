import { useState } from "react";

import { useCreateRequest, type RequestSummary } from "@/entities/request";

import { useRequestDraft } from "./draftStore";

/**
 * Publish the draft. Returns the created summary on success, or null when the
 * mutation rejected (the error is exposed on `error` for the preview sheet).
 */
export function useSubmitRequest(companyId: number) {
  const create = useCreateRequest(companyId);
  const toPayload = useRequestDraft((s) => s.toPayload);
  const [error, setError] = useState<Error | null>(null);

  async function submit(): Promise<RequestSummary | null> {
    setError(null);
    try {
      const payload = toPayload(companyId);
      // Catalog picks need grade OR polymer — `toPayload` sets polymer_type to
      // the sentinel "catalog". The free-typed path already required a grade.
      // When a catalog product was picked we also need a non-empty polymer that
      // isn't just a placeholder: prefer the product's code via product_id, and
      // keep polymer_type as a soft fallback the schema accepts.
      const saved = await create.mutateAsync(payload);
      return saved;
    } catch (err) {
      const e = err instanceof Error ? err : new Error(String(err));
      setError(e);
      return null;
    }
  }

  return {
    submit,
    error,
    isPending: create.isPending,
  };
}
