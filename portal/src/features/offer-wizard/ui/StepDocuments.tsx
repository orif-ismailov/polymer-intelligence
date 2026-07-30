import { useState } from "react";

import { useTranslation } from "react-i18next";

import { MAX_UPLOAD_BYTES, MAX_UPLOAD_MB } from "@/shared/config";
import { Alert, Dropzone, InfoIcon, StepPanel } from "@/shared/ui";

import {
  COUNTED_STEPS,
  DOCUMENT_MIME,
  OFFER_DOCUMENT_KINDS,
  REQUIRED_DOCUMENT_KINDS,
  STEP_DOCUMENTS,
  type OfferDocumentKind,
} from "../model/constants";
import { useOfferDraft } from "../model/draftStore";
import { missingDocumentKinds } from "../model/validation";
import { DocumentSlot } from "./DocumentSlot";
import { StepNav } from "./StepNav";

interface StepDocumentsProps {
  onNext: () => void;
  onBack: () => void;
}

/** Which slot a dropped file lands in — the first one still empty, in sheet order. */
function firstEmptySlot(present: ReadonlySet<OfferDocumentKind>): OfferDocumentKind | null {
  return OFFER_DOCUMENT_KINDS.find((kind) => !present.has(kind)) ?? null;
}

/** Sheet 4 — «Документы». */
export function StepDocuments({ onNext, onBack }: StepDocumentsProps) {
  const { t } = useTranslation();
  const documents = useOfferDraft((s) => s.documents);
  const serverFiles = useOfferDraft((s) => s.serverFiles);
  const setDocument = useOfferDraft((s) => s.setDocument);
  const [touched, setTouched] = useState(false);
  const [dropError, setDropError] = useState<string | null>(null);

  const serverByKind = new Map(
    serverFiles
      .filter((f): f is typeof f & { kind: OfferDocumentKind } =>
        (OFFER_DOCUMENT_KINDS as readonly string[]).includes(f.kind),
      )
      .map((f) => [f.kind, f]),
  );

  const present = new Set<OfferDocumentKind>(
    OFFER_DOCUMENT_KINDS.filter((kind) => documents[kind] != null || serverByKind.has(kind)),
  );
  const missing = missingDocumentKinds(present);

  function handleDrop(files: File[]): void {
    setDropError(null);
    let filled = new Set(present);
    for (const file of files) {
      if (file.size > MAX_UPLOAD_BYTES) {
        setDropError(t("offerWizard.documents.tooLarge", { mb: MAX_UPLOAD_MB }));
        continue;
      }
      const slot = firstEmptySlot(filled);
      if (slot === null) {
        setDropError(t("offerWizard.documents.allSlotsFull"));
        break;
      }
      setDocument(slot, file);
      filled = new Set([...filled, slot]);
    }
  }

  function handleNext(): void {
    setTouched(true);
    if (missing.length === 0) onNext();
  }

  return (
    <StepPanel
      step={STEP_DOCUMENTS}
      title={t("offerWizard.documents.title")}
      counter={t("offerWizard.stepOf", { current: STEP_DOCUMENTS, total: COUNTED_STEPS })}
      data-testid="offer-wizard-step-4"
    >
      <p className="mb-3 text-sm font-medium text-text">{t("offerWizard.documents.heading")}</p>

      <div className="space-y-4">
        {OFFER_DOCUMENT_KINDS.map((kind) => (
          <DocumentSlot
            key={kind}
            kind={kind}
            required={REQUIRED_DOCUMENT_KINDS.includes(kind)}
            serverFile={serverByKind.get(kind) ?? null}
            staged={documents[kind] ?? null}
          />
        ))}

        <Dropzone
          label={t("offerWizard.documents.dropLabel")}
          hint={t("offerWizard.documents.dropHint", { mb: MAX_UPLOAD_MB })}
          accept={DOCUMENT_MIME}
          multiple
          disabled={present.size >= OFFER_DOCUMENT_KINDS.length}
          onFiles={handleDrop}
          data-testid="offer-wizard-dropzone"
        />

        {dropError ? (
          <p role="alert" className="text-xs text-danger">
            {dropError}
          </p>
        ) : null}

        <p className="flex items-start gap-2 rounded-md border border-border bg-surface-inset px-3 py-2.5 text-xs leading-relaxed text-text-muted">
          <span className="mt-px shrink-0 text-info">
            <InfoIcon size={14} />
          </span>
          {t("offerWizard.documents.trustNote")}
        </p>

        {touched && missing.length > 0 ? (
          <Alert tone="warning" title={t("offerWizard.documents.missingTitle")}>
            {missing.map((kind) => t(`offerWizard.documents.kinds.${kind}`)).join(", ")}
          </Alert>
        ) : null}
      </div>

      <StepNav onNext={handleNext} onBack={onBack} />
    </StepPanel>
  );
}
