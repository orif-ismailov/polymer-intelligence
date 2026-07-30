import { useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import type { OfferFile } from "@/entities/offer";
import { MAX_UPLOAD_BYTES, MAX_UPLOAD_MB } from "@/shared/config";
import { formatBytes } from "@/shared/lib";
import {
  Badge,
  CheckCircleIcon,
  CloseIcon,
  FileIcon,
  FileRow,
} from "@/shared/ui";

import { DOCUMENT_MIME, type OfferDocumentKind } from "../model/constants";
import { useOfferDraft, type StagedFile } from "../model/draftStore";

interface DocumentSlotProps {
  kind: OfferDocumentKind;
  required: boolean;
  /** The file already on the server for this kind, if any. */
  serverFile: OfferFile | null;
  staged: StagedFile | null;
}

/**
 * One row of the «Обязательные документы» list: the document's name, and either
 * a pick affordance or the attached file with a ✕ and the green tick the mockup
 * puts to its right.
 *
 * The tick is not decoration — it is the only signal that a slot is answered,
 * and the sheet's «Далее» is gated on SDS and TDS having one.
 */
export function DocumentSlot({ kind, required, serverFile, staged }: DocumentSlotProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const setDocument = useOfferDraft((s) => s.setDocument);
  const removeServerFile = useOfferDraft((s) => s.removeServerFile);
  const [error, setError] = useState<string | null>(null);

  const present = staged !== null || serverFile !== null;

  function choose(file: File | undefined): void {
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setError(t("offerWizard.documents.tooLarge", { mb: MAX_UPLOAD_MB }));
      return;
    }
    setError(null);
    setDocument(kind, file);
  }

  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-sm font-medium text-text">
          {t(`offerWizard.documents.kinds.${kind}`)}
        </span>
        <Badge tone={required ? "warning" : "neutral"}>
          {required ? t("common.required") : t("common.optional")}
        </Badge>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={DOCUMENT_MIME}
        className="sr-only"
        onChange={(e) => {
          choose(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      {present ? (
        <div className="flex items-center gap-2">
          <FileRow
            className="min-w-0 flex-1"
            name={staged ? staged.file.name : (serverFile?.file_name ?? "")}
            meta={staged ? `${formatBytes(staged.file.size)} · PDF` : "PDF"}
            icon={<FileIcon size={18} />}
            actions={
              <button
                type="button"
                aria-label={t("common.remove")}
                onClick={() => {
                  if (staged) setDocument(kind, null);
                  else if (serverFile) removeServerFile(serverFile.id);
                }}
                className="rounded-full p-1 text-text-subtle transition-colors hover:bg-danger hover:text-danger-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <CloseIcon size={14} />
              </button>
            }
          />
          <span className="shrink-0 text-brand" aria-label={t("offerWizard.documents.attached")}>
            <CheckCircleIcon size={18} />
          </span>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex w-full items-center gap-3 rounded-md border border-dashed border-border-strong px-3 py-2.5 text-start transition-colors hover:border-brand-line hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          data-testid={`offer-wizard-doc-${kind}`}
        >
          <span className="text-text-subtle">
            <FileIcon size={18} />
          </span>
          <span className="text-sm text-text-muted">{t("offerWizard.documents.pick")}</span>
        </button>
      )}

      {error ? (
        <p role="alert" className="mt-1 text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
