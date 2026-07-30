import { useCallback, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { offerApi, offerKeys, type CompanyOffer } from "@/entities/offer";
import { ApiError } from "@/shared/api";

import { OFFER_DOCUMENT_KINDS } from "./constants";
import { draftToPayload, useOfferDraft } from "./draftStore";

/** The API's typed refusal when the publishing company is not verified yet. */
export function isNotVerifiedError(error: unknown): boolean {
  return error instanceof ApiError && error.code === "company_not_verified";
}

/** Longest edge after the client-side downscale, matching the old photo section. */
const MAX_EDGE_PX = 1600;
const MAX_PHOTO_BYTES = 10 * 1024 * 1024;

/**
 * Shrink an oversized picture before uploading. Phone cameras produce 4–8 MB
 * frames that would hit the server cap for no visual gain; the server stays the
 * authority on size and type, so any failure here just sends the original.
 */
async function downscale(file: File): Promise<File> {
  if (!file.type.startsWith("image/")) return file;
  try {
    const bitmap = await createImageBitmap(file);
    const longest = Math.max(bitmap.width, bitmap.height);
    if (longest <= MAX_EDGE_PX && file.size <= MAX_PHOTO_BYTES) {
      bitmap.close();
      return file;
    }
    const scale = Math.min(1, MAX_EDGE_PX / longest);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, file.type, 0.85);
    });
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], file.name, { type: file.type });
  } catch {
    return file;
  }
}

export interface SubmitProgress {
  /** What the button says it is doing right now. */
  phase: "idle" | "saving" | "uploading" | "finishing";
  /** Files uploaded so far / to upload, for the progress line. */
  uploaded: number;
  total: number;
}

/**
 * Publish (or re-save) the drafted offer.
 *
 * The whole sheet is committed in one gesture, in a fixed order:
 *
 *   1. create or PATCH the offer — nothing else can happen without its id;
 *   2. delete the server files the seller removed;
 *   3. upload the staged photos IN ORDER (the first one is the cover, so a
 *      parallel loop would race for that slot), then the documents, then the
 *      laboratory passport;
 *   4. if the publish gate held the offer as a `draft` for want of a document
 *      that has just been uploaded, PATCH once more so the gate re-runs.
 *
 * Step 4 is the one that is easy to miss: `apply_publish_gate` runs on save, and
 * on a NEW offer the documents cannot exist yet — the SDS a `docs_required`
 * substance needs is uploaded in step 3, after the verdict was taken. Without
 * the re-save the seller would land on the published sheet looking at a draft
 * whose only fault was the order we do things in.
 */
export function useSubmitOffer(companyId: number) {
  const queryClient = useQueryClient();
  const [progress, setProgress] = useState<SubmitProgress>({
    phase: "idle",
    uploaded: 0,
    total: 0,
  });
  const [error, setError] = useState<Error | null>(null);

  const submit = useCallback(async (): Promise<CompanyOffer | null> => {
    const { draft, offerId, photos, documents, labPassport, removedFileIds } =
      useOfferDraft.getState();
    const payload = draftToPayload(draft);

    const staged = [
      ...photos.map((entry) => ({ file: entry.file, kind: "image" as const })),
      ...OFFER_DOCUMENT_KINDS.flatMap((kind) => {
        const entry = documents[kind];
        return entry ? [{ file: entry.file, kind }] : [];
      }),
      ...(labPassport ? [{ file: labPassport.file, kind: "lab_passport" as const }] : []),
    ];

    setError(null);
    setProgress({ phase: "saving", uploaded: 0, total: staged.length });

    try {
      let offer =
        offerId == null
          ? await offerApi.create(companyId, payload)
          : await offerApi.update(companyId, offerId, payload);

      for (const fileId of removedFileIds) {
        offer = await offerApi.deleteFile(companyId, offer.id, fileId);
      }

      if (staged.length > 0) {
        setProgress({ phase: "uploading", uploaded: 0, total: staged.length });
        for (const [index, item] of staged.entries()) {
          const prepared = item.kind === "image" ? await downscale(item.file) : item.file;
          offer = await offerApi.uploadFile(companyId, offer.id, prepared, item.kind);
          setProgress({ phase: "uploading", uploaded: index + 1, total: staged.length });
        }

        if (offer.status === "draft" && offer.compliance_ok === false) {
          setProgress({ phase: "finishing", uploaded: staged.length, total: staged.length });
          offer = await offerApi.update(companyId, offer.id, payload);
        }
      }

      void queryClient.invalidateQueries({ queryKey: offerKeys.list(companyId) });
      queryClient.setQueryData(offerKeys.detail(companyId, offer.id), offer);
      setProgress({ phase: "idle", uploaded: 0, total: 0 });
      return offer;
    } catch (err) {
      setProgress({ phase: "idle", uploaded: 0, total: 0 });
      setError(err instanceof Error ? err : new Error(String(err)));
      return null;
    }
  }, [companyId, queryClient]);

  return {
    submit,
    progress,
    error,
    isPending: progress.phase !== "idle",
    notVerified: isNotVerifiedError(error),
  };
}
