import { useState } from "react";

import { useTranslation } from "react-i18next";

import { DocumentDropzone } from "@/features/upload-document";
import { Alert, Button } from "@/shared/ui";

import { WIZARD_DOCUMENT_KINDS } from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { areDocumentsValid, requiredDocumentKinds } from "../model/validation";

interface StepDocumentsProps {
  onNext: () => void;
  onBack: () => void;
}

/**
 * Step 4 — «Документы». Like the bank step this is not one of the mockup's four
 * sheets; it feeds the case's `documents_complete` check, which is what turns a
 * submitted company into a verified one.
 */
export function StepDocuments({ onNext, onBack }: StepDocumentsProps) {
  const { t } = useTranslation();
  const bank = useWizardDraft((s) => s.bank);
  const documents = useWizardDraft((s) => s.documents);
  const setDocument = useWizardDraft((s) => s.setDocument);
  const identityLocked = useWizardDraft((s) => s.identityLocked);
  const [touched, setTouched] = useState(false);

  const required = new Set(requiredDocumentKinds(bank, identityLocked));
  const valid = areDocumentsValid(documents, bank, identityLocked);

  function handleNext(): void {
    setTouched(true);
    if (valid) onNext();
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.documents.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.documents.subtitle")}</p>
      </div>

      <ul className="space-y-1 text-sm text-text-muted">
        {identityLocked ? (
          <li>• {t("wizard.documents.eimzoWaived")}</li>
        ) : (
          <li>• {t("wizard.documents.registrationRequired")}</li>
        )}
        {bank.enabled ? <li>• {t("wizard.documents.bankLetterRequired")}</li> : null}
      </ul>

      <div className="space-y-4">
        {WIZARD_DOCUMENT_KINDS.map((kind) => (
          <DocumentDropzone
            key={kind}
            kind={kind}
            required={required.has(kind)}
            file={documents[kind] ?? null}
            onSelect={(file) => setDocument(kind, file)}
            onClear={() => setDocument(kind, null)}
          />
        ))}
      </div>

      {touched && !valid ? (
        <Alert tone="warning" title={t("wizard.errors.missingRequiredDocs")} />
      ) : null}

      <div className="flex gap-3">
        <Button variant="ghost" size="lg" onClick={onBack} className="min-w-24">
          {t("common.back")}
        </Button>
        <Button size="lg" onClick={handleNext} disabled={!valid} className="flex-1" data-testid="wizard-next">
          {t("common.next")}
        </Button>
      </div>
    </div>
  );
}
