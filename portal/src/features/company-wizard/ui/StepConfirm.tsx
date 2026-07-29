import { useTranslation } from "react-i18next";

import { useEnumLabels } from "@/shared/i18n";
import { Alert, Button } from "@/shared/ui";

import { useWizardDraft } from "../model/draftStore";
import { useSubmitWizard } from "../model/useSubmitWizard";

interface StepConfirmProps {
  onBack: () => void;
  onEditStep: (step: number) => void;
  onComplete: (companyId: number) => void;
}

interface ReviewRowProps {
  label: string;
  value: string;
}

function ReviewRow({ label, value }: ReviewRowProps) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <dt className="text-text-muted">{label}</dt>
      <dd className="text-right font-medium text-text">{value || "—"}</dd>
    </div>
  );
}

interface SectionProps {
  title: string;
  step: number;
  onEditStep: (step: number) => void;
  children: React.ReactNode;
}

function Section({ title, step, onEditStep, children }: SectionProps) {
  const { t } = useTranslation();
  return (
    <section className="rounded-md border border-border bg-surface-2 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        <button
          type="button"
          onClick={() => onEditStep(step)}
          className="text-xs font-medium text-brand hover:underline"
        >
          {t("wizard.confirm.editStep")}
        </button>
      </div>
      <dl>{children}</dl>
    </section>
  );
}

export function StepConfirm({ onBack, onEditStep, onComplete }: StepConfirmProps) {
  const { t } = useTranslation();
  const label = useEnumLabels();
  const { identity, roles, bank, documents } = useWizardDraft();
  const { submit, isSubmitting, error } = useSubmitWizard();

  const documentEntries = Object.entries(documents).filter(([, file]) => file instanceof File);

  async function handleSubmit(): Promise<void> {
    const companyId = await submit();
    if (companyId != null) onComplete(companyId);
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-text">{t("wizard.confirm.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.confirm.subtitle")}</p>
      </div>

      <div className="space-y-3">
        <Section title={t("wizard.confirm.identitySection")} step={1} onEditStep={onEditStep}>
          <ReviewRow label={t("companies.jurisdiction")} value={label("jurisdiction", identity.jurisdiction)} />
          <ReviewRow label={t("companies.taxId")} value={identity.tax_id} />
          <ReviewRow label={t("companies.legalName")} value={identity.legal_name} />
          <ReviewRow label={t("company.legalForm")} value={identity.legal_form} />
          <ReviewRow label={t("company.director")} value={identity.director_name} />
          <ReviewRow label={t("company.legalAddress")} value={identity.legal_address} />
        </Section>

        <Section title={t("wizard.confirm.rolesSection")} step={2} onEditStep={onEditStep}>
          <ReviewRow
            label={t("company.roles")}
            value={roles.map((r) => label("businessRole", r)).join(", ")}
          />
        </Section>

        <Section title={t("wizard.confirm.bankSection")} step={3} onEditStep={onEditStep}>
          {bank.enabled ? (
            <>
              <ReviewRow label={t("company.bankMfo")} value={bank.bank_mfo} />
              <ReviewRow label={t("company.accountNumber")} value={bank.account_number} />
              <ReviewRow label={t("company.currency")} value={bank.currency} />
            </>
          ) : (
            <p className="text-sm text-text-muted">{t("wizard.confirm.noBank")}</p>
          )}
        </Section>

        <Section title={t("wizard.confirm.documentsSection")} step={4} onEditStep={onEditStep}>
          {documentEntries.length > 0 ? (
            documentEntries.map(([kind, file]) => (
              <ReviewRow key={kind} label={label("documentKind", kind)} value={file?.name ?? ""} />
            ))
          ) : (
            <p className="text-sm text-text-muted">{t("company.noDocuments")}</p>
          )}
        </Section>
      </div>

      {error ? (
        <Alert tone="danger" title={t(error.messageKey, error.messageValues ?? {})}>
          {error.detail}
        </Alert>
      ) : null}

      <div className="flex justify-between border-t border-border pt-4">
        <Button variant="ghost" onClick={onBack} disabled={isSubmitting}>
          {t("common.back")}
        </Button>
        <Button
          onClick={() => void handleSubmit()}
          loading={isSubmitting}
          className="min-w-56"
          data-testid="wizard-submit"
        >
          {isSubmitting ? t("wizard.confirm.submitting") : t("wizard.confirm.submit")}
        </Button>
      </div>
    </div>
  );
}
