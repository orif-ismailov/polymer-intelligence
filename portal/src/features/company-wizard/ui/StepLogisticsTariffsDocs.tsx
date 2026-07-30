import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { DocumentDropzone } from "@/features/upload-document";
import { Alert, Button, Radio } from "@/shared/ui";

import { LOGISTICS_DOC_KINDS, LOGISTICS_TARIFF_MODELS } from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { areDocumentsValid, isLogisticsTariffsValid } from "../model/validation";

interface StepLogisticsTariffsDocsProps {
  onNext: () => void;
  onBack: () => void;
}

/**
 * Logistics step 6 — tariff model + carrier documents from logist_reg_flow.jpeg.
 * Carrier docs are optional to advance; registration certificate is required
 * when E-IMZO has not locked identity.
 */
export function StepLogisticsTariffsDocs({ onNext, onBack }: StepLogisticsTariffsDocsProps) {
  const { t } = useTranslation();
  const logistics = useWizardDraft((s) => s.logistics);
  const setLogistics = useWizardDraft((s) => s.setLogistics);
  const documents = useWizardDraft((s) => s.documents);
  const setDocument = useWizardDraft((s) => s.setDocument);
  const bank = useWizardDraft((s) => s.bank);
  const identityLocked = useWizardDraft((s) => s.identityLocked);
  const accountType = useWizardDraft((s) => s.accountType);
  const [submitted, setSubmitted] = useState(false);

  const kinds = identityLocked
    ? [...LOGISTICS_DOC_KINDS]
    : (["registration_certificate", ...LOGISTICS_DOC_KINDS] as const);

  const tariffsOk = isLogisticsTariffsValid(logistics);
  const docsOk = areDocumentsValid(documents, bank, identityLocked, accountType);
  const valid = tariffsOk && docsOk;

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    setSubmitted(true);
    if (valid) onNext();
  }

  return (
    <form className="space-y-6" onSubmit={handleSubmit} noValidate>
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.logistics.tariffs.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.logistics.tariffs.subtitle")}</p>
      </div>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-text">
          {t("wizard.logistics.tariffs.tariffsSection")}
        </h3>
        <p className="text-sm text-text-muted">{t("wizard.logistics.tariffs.tariffsHint")}</p>
        {submitted && !tariffsOk ? (
          <p className="text-sm text-danger">{t("wizard.logistics.tariffs.required")}</p>
        ) : null}
        <div className="space-y-2" role="radiogroup" aria-label={t("wizard.logistics.tariffs.tariffsSection")}>
          {LOGISTICS_TARIFF_MODELS.map((model) => (
            <Radio
              key={model}
              id={`logistics-tariff-${model}`}
              name="logistics-tariff"
              label={t(`wizard.logistics.tariffs.models.${model}`)}
              checked={logistics.tariff_model === model}
              onChange={() => setLogistics({ tariff_model: model })}
            />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-text">
          {t("wizard.logistics.tariffs.docsSection")}
        </h3>
        <p className="text-sm text-text-muted">{t("wizard.logistics.tariffs.docsHint")}</p>

        {identityLocked ? (
          <Alert tone="success" title={t("wizard.documents.eimzoWaived")} />
        ) : null}

        {submitted && !docsOk ? (
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

        <Alert tone="info">{t("wizard.logistics.tariffs.moderationNote")}</Alert>
      </section>

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
          {t("wizard.logistics.tariffs.next")}
        </Button>
      </div>
    </form>
  );
}
