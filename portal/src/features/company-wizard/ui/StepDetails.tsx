import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { JURISDICTIONS } from "@/shared/config";
import {
  Alert,
  Button,
  DateInput,
  FormField,
  Input,
  MapPinIcon,
  Select,
  Textarea,
} from "@/shared/ui";
import type { SelectOption } from "@/shared/ui";

import { LEGAL_FORMS } from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { useEnumOptions } from "../model/useEnumOptions";
import { isIdentityValid, isRegistrationDateValid, isTaxIdValid } from "../model/validation";

interface StepDetailsProps {
  onNext: () => void;
  onBack: () => void;
}

/** Step 2 — «Основная информация»: the six required fields from the mockup. */
export function StepDetails({ onNext, onBack }: StepDetailsProps) {
  const { t } = useTranslation();
  const identity = useWizardDraft((s) => s.identity);
  const setIdentity = useWizardDraft((s) => s.setIdentity);
  const identityLocked = useWizardDraft((s) => s.identityLocked);
  const jurisdictionOptions = useEnumOptions("jurisdiction", JURISDICTIONS);
  /**
   * Per-field, not per-step. A single step-wide flag meant blurring the ИНН field —
   * the only field that set it — painted every other required field red at once,
   * including ones the user had never visited. `submitted` is the escape hatch:
   * pressing «Далее» reveals everything that is still missing.
   */
  const [blurred, setBlurred] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);
  const show = (field: string): boolean => submitted || Boolean(blurred[field]);
  const markBlurred = (field: string) => () =>
    setBlurred((prev) => (prev[field] ? prev : { ...prev, [field]: true }));

  const taxOk = isTaxIdValid(identity);
  const dateOk = isRegistrationDateValid(identity.registration_date);
  const valid = isIdentityValid(identity);

  /*
   * `legal_form` is free text on the server and predates this select, so a value
   * the option list does not know (an older row, or an E-IMZO-filled one) is
   * offered back as its own option. Without this the select would silently
   * re-point at the first option and the next PATCH would overwrite it.
   */
  const legalFormOptions: SelectOption[] = [
    ...LEGAL_FORMS.map((form) => ({ value: form, label: t(`company.legalForms.${form}`) })),
    ...(identity.legal_form && !LEGAL_FORMS.includes(identity.legal_form as (typeof LEGAL_FORMS)[number])
      ? [{ value: identity.legal_form, label: identity.legal_form }]
      : []),
  ];

  function handleNext(): void {
    setSubmitted(true);
    if (valid) onNext();
  }

  /**
   * A real `<form>` so Enter in any field advances the step. The wizard steps were
   * plain `<div>`s, which meant keyboard users had to Tab past every remaining
   * field to reach «Далее» — the one interaction a form gives you for free.
   */
  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    handleNext();
  }

  return (
    <form className="space-y-6" onSubmit={handleSubmit} noValidate>
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.details.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.details.subtitle")}</p>
      </div>

      {identityLocked ? (
        <Alert tone="success" title={t("wizard.details.lockedTitle")} data-testid="wizard-identity-locked">
          {t("wizard.details.lockedBody")}
        </Alert>
      ) : null}

      <div className="space-y-5">
        <FormField
          label={t("wizard.details.fields.legalName")}
          required
          error={show("legal_name") && identity.legal_name.trim() === "" ? t("wizard.details.legalNameRequired") : null}
        >
          {({ id, invalid, describedBy, required }) => (
            <Input
              id={id}
              aria-required={required}
              value={identity.legal_name}
              invalid={invalid}
              aria-describedby={describedBy}
              disabled={identityLocked}
              onChange={(e) => setIdentity({ legal_name: e.target.value })}
              onBlur={markBlurred("legal_name")}
            />
          )}
        </FormField>

        <FormField label={t("wizard.details.fields.country")} required>
          {({ id, required }) => (
            <Select
              id={id}
              aria-required={required}
              options={jurisdictionOptions}
              value={identity.jurisdiction}
              disabled={identityLocked}
              onChange={(e) => setIdentity({ jurisdiction: e.target.value })}
            />
          )}
        </FormField>

        <FormField
          label={t("wizard.details.fields.taxId")}
          required
          error={show("tax_id") && !taxOk ? t("wizard.details.taxIdInvalid") : null}
        >
          {({ id, invalid, describedBy, required }) => (
            <Input
              id={id}
              aria-required={required}
              inputMode="numeric"
              value={identity.tax_id}
              invalid={invalid}
              aria-describedby={describedBy}
              disabled={identityLocked}
              onChange={(e) => setIdentity({ tax_id: e.target.value.replace(/\s+/g, "") })}
              onBlur={markBlurred("tax_id")}
            />
          )}
        </FormField>

        <FormField
          label={t("wizard.details.fields.address")}
          required
          error={
            show("legal_address") && identity.legal_address.trim() === ""
              ? t("wizard.details.addressRequired")
              : null
          }
        >
          {({ id, invalid, describedBy, required }) => (
            <Textarea
              id={id}
              aria-required={required}
              rows={2}
              value={identity.legal_address}
              invalid={invalid}
              aria-describedby={describedBy}
              trailing={<MapPinIcon size={18} />}
              onChange={(e) => setIdentity({ legal_address: e.target.value })}
              onBlur={markBlurred("legal_address")}
            />
          )}
        </FormField>

        <FormField
          label={t("wizard.details.fields.registrationDate")}
          required
          error={show("registration_date") && !dateOk ? t("wizard.details.registrationDateInvalid") : null}
        >
          {({ id, invalid, describedBy, required }) => (
            <DateInput
              id={id}
              aria-required={required}
              max={new Date().toISOString().slice(0, 10)}
              value={identity.registration_date}
              invalid={invalid}
              aria-describedby={describedBy}
              pickerLabel={t("common.pickDate")}
              onChange={(e) => setIdentity({ registration_date: e.target.value })}
              onBlur={markBlurred("registration_date")}
            />
          )}
        </FormField>

        <FormField
          label={t("wizard.details.fields.ownershipForm")}
          required
          error={show("legal_form") && identity.legal_form.trim() === "" ? t("wizard.details.legalFormRequired") : null}
        >
          {({ id, invalid, describedBy, required }) => (
            <Select
              id={id}
              aria-required={required}
              options={legalFormOptions}
              placeholder={t("wizard.details.legalFormPlaceholder")}
              value={identity.legal_form}
              invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => setIdentity({ legal_form: e.target.value })}
              onBlur={markBlurred("legal_form")}
            />
          )}
        </FormField>
      </div>

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
