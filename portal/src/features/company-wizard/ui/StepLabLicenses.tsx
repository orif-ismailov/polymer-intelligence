import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { DocumentDropzone } from "@/features/upload-document";
import { Alert, Button } from "@/shared/ui";

import { LABORATORY_DOC_KINDS } from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { areDocumentsValid } from "../model/validation";

interface StepLabLicensesProps {
  onNext: () => void;
  onBack: () => void;
}

/**
 * Laboratory licenses step — accreditation document slots from
 * `labaratory_reg_flow.jpeg` «Аккредитации и документы», plus the registration
 * certificate when E-IMZO has not already locked identity.
 */
export function StepLabLicenses({ onNext, onBack }: StepLabLicensesProps) {
  const { t } = useTranslation();
  const documents = useWizardDraft((s) => s.documents);
  const setDocument = useWizardDraft((s) => s.setDocument);
  const bank = useWizardDraft((s) => s.bank);
  const identityLocked = useWizardDraft((s) => s.identityLocked);
  const accountType = useWizardDraft((s) => s.accountType);
  const [submitted, setSubmitted] = useState(false);

  const kinds = identityLocked
    ? [...LABORATORY_DOC_KINDS]
    : (["registration_certificate", ...LABORATORY_DOC_KINDS] as const);

  const valid = areDocumentsValid(documents, bank, identityLocked, accountType);

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    setSubmitted(true);
    if (valid) onNext();
  }

  return (
    <form className="space-y-6" onSubmit={handleSubmit} noValidate>
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.labDocs.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.labDocs.subtitle")}</p>
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

      <Alert tone="info">{t("wizard.labDocs.moderationNote")}</Alert>

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
          {t("wizard.laboratory.licenses.next")}
        </Button>
      </div>
    </form>
  );
}
