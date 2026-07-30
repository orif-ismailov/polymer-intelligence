import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { DocumentDropzone } from "@/features/upload-document";
import { Alert, Button } from "@/shared/ui";

import { MANUFACTURER_CERT_KINDS } from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { areDocumentsValid } from "../model/validation";

interface StepManufacturerCertsProps {
  onNext: () => void;
  onBack: () => void;
}

/**
 * Manufacturer certificates step — six factory document slots from the mockup,
 * plus the registration certificate when E-IMZO has not already locked identity.
 */
export function StepManufacturerCerts({ onNext, onBack }: StepManufacturerCertsProps) {
  const { t } = useTranslation();
  const documents = useWizardDraft((s) => s.documents);
  const setDocument = useWizardDraft((s) => s.setDocument);
  const bank = useWizardDraft((s) => s.bank);
  const identityLocked = useWizardDraft((s) => s.identityLocked);
  const accountType = useWizardDraft((s) => s.accountType);
  const [submitted, setSubmitted] = useState(false);

  const kinds = identityLocked
    ? [...MANUFACTURER_CERT_KINDS]
    : (["registration_certificate", ...MANUFACTURER_CERT_KINDS] as const);

  const valid = areDocumentsValid(documents, bank, identityLocked, accountType);

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    setSubmitted(true);
    if (valid) onNext();
  }

  return (
    <form className="space-y-6" onSubmit={handleSubmit} noValidate>
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.mfrDocs.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.mfrDocs.subtitle")}</p>
      </div>

      {identityLocked ? (
        <Alert tone="success" title={t("wizard.documents.eimzoWaived")} />
      ) : null}

      {submitted && !valid ? (
        <Alert tone="danger">{t("wizard.documents.registrationRequired")}</Alert>
      ) : null}

      <div className="space-y-3">
        {kinds.map((kind) => (
          <DocumentDropzone
            key={kind}
            kind={kind}
            required={kind === "registration_certificate" && !identityLocked}
            file={documents[kind] ?? null}
            onSelect={(file) => setDocument(kind, file)}
            onClear={() => setDocument(kind, null)}
          />
        ))}
      </div>

      <Alert tone="info">{t("wizard.mfrDocs.moderationNote")}</Alert>

      <div className="flex gap-3">
        <Button type="button" variant="ghost" size="lg" onClick={onBack} className="min-w-24">
          {t("common.back")}
        </Button>
        <Button
          type="submit"
          size="lg"
          disabled={!valid}
          className="flex-1"
          data-testid="wizard-next"
        >
          {t("common.next")}
        </Button>
      </div>
    </form>
  );
}
