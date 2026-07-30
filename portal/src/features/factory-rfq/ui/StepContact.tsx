import { useState } from "react";

import { useTranslation } from "react-i18next";

import { Alert, FormField, Input } from "@/shared/ui";

import { COUNTED_STEPS, STEP_CONTACT } from "../model/constants";
import { isContactValid, useFactoryRfqDraft } from "../model/draftStore";
import { StepNav } from "./StepNav";

interface StepContactProps {
  error: Error | null;
  isPending: boolean;
  onSubmit: () => void;
  onBack: () => void;
}

/** Sheet 4 — contact person. Name and phone are required; submits the RFQ. */
export function StepContact({ error, isPending, onSubmit, onBack }: StepContactProps) {
  const { t } = useTranslation();
  const draft = useFactoryRfqDraft((s) => s.draft);
  const setField = useFactoryRfqDraft((s) => s.setField);
  const [touched, setTouched] = useState(false);

  function handleSubmit(): void {
    setTouched(true);
    if (isContactValid(draft)) onSubmit();
  }

  const nameMissing = touched && draft.contactName.trim() === "";
  const phoneMissing = touched && draft.contactPhone.trim() === "";

  return (
    <div className="space-y-5" data-testid="factory-rfq-step-4">
      <header>
        <p className="num text-xs text-text-muted">
          {t("factoryRfq.stepOf", { current: STEP_CONTACT, total: COUNTED_STEPS })}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-text">{t("factoryRfq.contact.title")}</h2>
      </header>

      <FormField
        label={t("factoryRfq.contact.name")}
        required
        error={nameMissing ? t("factoryRfq.contact.nameRequired") : null}
      >
        {({ id, invalid }) => (
          <Input
            id={id}
            value={draft.contactName}
            onChange={(e) => setField("contactName", e.target.value)}
            invalid={invalid}
            data-testid="factory-rfq-contact-name"
          />
        )}
      </FormField>

      <FormField label={t("factoryRfq.contact.position")}>
        {({ id }) => (
          <Input
            id={id}
            value={draft.contactPosition}
            onChange={(e) => setField("contactPosition", e.target.value)}
          />
        )}
      </FormField>

      <FormField label={t("factoryRfq.contact.email")}>
        {({ id }) => (
          <Input
            id={id}
            type="email"
            value={draft.contactEmail}
            onChange={(e) => setField("contactEmail", e.target.value)}
          />
        )}
      </FormField>

      <FormField
        label={t("factoryRfq.contact.phone")}
        required
        error={phoneMissing ? t("factoryRfq.contact.phoneRequired") : null}
      >
        {({ id, invalid }) => (
          <Input
            id={id}
            type="tel"
            value={draft.contactPhone}
            onChange={(e) => setField("contactPhone", e.target.value)}
            invalid={invalid}
            data-testid="factory-rfq-contact-phone"
          />
        )}
      </FormField>

      <FormField label={t("factoryRfq.contact.telegram")}>
        {({ id }) => (
          <Input
            id={id}
            value={draft.contactTelegram}
            onChange={(e) => setField("contactTelegram", e.target.value)}
            placeholder="@username"
          />
        )}
      </FormField>

      {error ? (
        <Alert tone="danger" title={t("errors.generic")}>
          {error.message || t("factoryRfq.submitFailed")}
        </Alert>
      ) : null}

      <StepNav
        onNext={handleSubmit}
        onBack={onBack}
        disabled={isPending}
        loading={isPending}
        variant="gold"
        nextLabel={isPending ? t("common.saving") : t("factoryRfq.contact.submit")}
        data-testid="factory-rfq-submit"
      />
    </div>
  );
}
