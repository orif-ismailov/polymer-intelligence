import { type FormEvent, useEffect, useMemo, useState } from "react";

import { useTranslation } from "react-i18next";

import { JURISDICTIONS } from "@/shared/config";
import {
  Alert,
  Button,
  DateInput,
  Dropzone,
  FormField,
  Input,
  MapPinIcon,
  Select,
  Textarea,
} from "@/shared/ui";
import type { SelectOption } from "@/shared/ui";

import {
  LEGAL_FORMS,
  isLaboratoryType,
  isLogisticsType,
  isManufacturerType,
} from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { useEnumOptions } from "../model/useEnumOptions";
import {
  isIdentityValidForType,
  isRegistrationDateValid,
  isTaxIdValid,
} from "../model/validation";

import { RegistryPrefillNotice } from "./RegistryPrefillNotice";

interface StepDetailsProps {
  onNext: () => void;
  onBack: () => void;
}

/**
 * Step 2 — company identity.
 *
 * Default types keep the shared «Основная информация» sheet. Manufacturer
 * follows `companys_list.jpeg`. Logistics follows `logist_reg_flow.jpeg`.
 * Laboratory follows `labaratory_reg_flow.jpeg`: logo + name + country + city +
 * website + legal address + email + phone + description. Logo is available for
 * every account type.
 */
export function StepDetails({ onNext, onBack }: StepDetailsProps) {
  const { t } = useTranslation();
  const identity = useWizardDraft((s) => s.identity);
  const setIdentity = useWizardDraft((s) => s.setIdentity);
  const identityLocked = useWizardDraft((s) => s.identityLocked);
  const accountType = useWizardDraft((s) => s.accountType);
  const logistics = useWizardDraft((s) => s.logistics);
  const setLogistics = useWizardDraft((s) => s.setLogistics);
  const laboratory = useWizardDraft((s) => s.laboratory);
  const setLaboratory = useWizardDraft((s) => s.setLaboratory);
  const logo = useWizardDraft((s) => s.logo);
  const setLogo = useWizardDraft((s) => s.setLogo);
  const manufacturer = isManufacturerType(accountType);
  const logisticsFlow = isLogisticsType(accountType);
  const laboratoryFlow = isLaboratoryType(accountType);
  const jurisdictionOptions = useEnumOptions("jurisdiction", JURISDICTIONS);
  const [blurred, setBlurred] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);

  useEffect(() => {
    if (!logo) {
      setLogoPreview(null);
      return;
    }
    const url = URL.createObjectURL(logo);
    setLogoPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [logo]);

  const show = (field: string): boolean => submitted || Boolean(blurred[field]);
  const markBlurred = (field: string) => () =>
    setBlurred((prev) => (prev[field] ? prev : { ...prev, [field]: true }));

  const taxOk = isTaxIdValid(identity);
  const dateOk = isRegistrationDateValid(identity.registration_date);
  const valid = isIdentityValidForType(identity, accountType, logistics, laboratory);

  const legalFormOptions: SelectOption[] = [
    ...LEGAL_FORMS.map((form) => ({ value: form, label: t(`company.legalForms.${form}`) })),
    ...(identity.legal_form && !LEGAL_FORMS.includes(identity.legal_form as (typeof LEGAL_FORMS)[number])
      ? [{ value: identity.legal_form, label: identity.legal_form }]
      : []),
  ];

  const title = manufacturer
    ? t("wizard.details.manufacturerTitle")
    : logisticsFlow
      ? t("wizard.details.logisticsTitle")
      : laboratoryFlow
        ? t("wizard.details.laboratoryTitle")
        : t("wizard.details.title");
  const subtitle = manufacturer
    ? t("wizard.details.manufacturerSubtitle")
    : logisticsFlow
      ? t("wizard.details.logisticsSubtitle")
      : laboratoryFlow
        ? t("wizard.details.laboratorySubtitle")
        : t("wizard.details.subtitle");

  function handleNext(): void {
    setSubmitted(true);
    if (valid) onNext();
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    handleNext();
  }

  const logoHint = useMemo(() => t("wizard.details.logoHint"), [t]);
  const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(laboratory.email.trim());

  return (
    <form className="space-y-6" onSubmit={handleSubmit} noValidate>
      <div>
        <h2 className="text-lg font-semibold text-text">{title}</h2>
        <p className="mt-1 text-sm text-text-muted">{subtitle}</p>
      </div>

      {identityLocked ? (
        <Alert tone="success" title={t("wizard.details.lockedTitle")} data-testid="wizard-identity-locked">
          {t("wizard.details.lockedBody")}
        </Alert>
      ) : null}

      <RegistryPrefillNotice />

      <div className="space-y-5">
        <FormField label={t("wizard.details.fields.logo")}>
          {() => (
            <div className="space-y-3">
              {logoPreview ? (
                <div className="flex items-center gap-3">
                  <img
                    src={logoPreview}
                    alt=""
                    className="h-16 w-16 rounded-md border border-border object-cover"
                  />
                  <Button type="button" variant="ghost" size="sm" onClick={() => setLogo(null)}>
                    {t("wizard.details.logoRemove")}
                  </Button>
                </div>
              ) : (
                <Dropzone
                  label={t("wizard.details.logoUpload")}
                  hint={logoHint}
                  accept="image/jpeg,image/png,.jpg,.jpeg,.png"
                  onFiles={(files) => setLogo(files[0] ?? null)}
                  data-testid="wizard-logo-dropzone"
                />
              )}
            </div>
          )}
        </FormField>

        <FormField
          label={
            manufacturer
              ? t("wizard.details.fields.factoryLegalName")
              : laboratoryFlow
                ? t("wizard.details.fields.laboratoryName")
                : t("wizard.details.fields.legalName")
          }
          required
          error={
            show("legal_name") && identity.legal_name.trim() === ""
              ? t("wizard.details.legalNameRequired")
              : null
          }
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

        {manufacturer ? (
          <FormField label={t("wizard.details.fields.commercialName")}>
            {({ id }) => (
              <Input
                id={id}
                value={identity.short_name}
                onChange={(e) => setIdentity({ short_name: e.target.value })}
              />
            )}
          </FormField>
        ) : null}

        {!manufacturer ? (
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
        ) : null}

        {logisticsFlow ? (
          <FormField
            label={t("wizard.details.fields.city")}
            required
            error={
              show("city") && logistics.city.trim() === ""
                ? t("wizard.details.cityRequired")
                : null
            }
          >
            {({ id, invalid, describedBy, required }) => (
              <Input
                id={id}
                aria-required={required}
                value={logistics.city}
                invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setLogistics({ city: e.target.value })}
                onBlur={markBlurred("city")}
              />
            )}
          </FormField>
        ) : null}

        {laboratoryFlow ? (
          <FormField
            label={t("wizard.details.fields.city")}
            required
            error={
              show("lab_city") && laboratory.city.trim() === ""
                ? t("wizard.details.cityRequired")
                : null
            }
          >
            {({ id, invalid, describedBy, required }) => (
              <Input
                id={id}
                aria-required={required}
                value={laboratory.city}
                invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setLaboratory({ city: e.target.value })}
                onBlur={markBlurred("lab_city")}
              />
            )}
          </FormField>
        ) : null}

        {laboratoryFlow ? (
          <FormField label={t("wizard.details.fields.website")}>
            {({ id }) => (
              <Input
                id={id}
                type="url"
                inputMode="url"
                placeholder="www.example.com"
                value={laboratory.website}
                onChange={(e) => setLaboratory({ website: e.target.value })}
              />
            )}
          </FormField>
        ) : null}

        {manufacturer ? (
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
        ) : null}

        {manufacturer ? (
          <FormField
            label={t("wizard.details.fields.registrationNumber")}
            required
            error={
              show("registration_number") && identity.registration_number.trim() === ""
                ? t("wizard.details.registrationNumberRequired")
                : null
            }
          >
            {({ id, invalid, describedBy, required }) => (
              <Input
                id={id}
                aria-required={required}
                value={identity.registration_number}
                invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setIdentity({ registration_number: e.target.value })}
                onBlur={markBlurred("registration_number")}
              />
            )}
          </FormField>
        ) : null}

        {manufacturer ? (
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
        ) : null}

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

        {laboratoryFlow ? (
          <FormField
            label={t("wizard.details.fields.email")}
            required
            error={
              show("lab_email") && !emailOk ? t("wizard.details.emailInvalid") : null
            }
          >
            {({ id, invalid, describedBy, required }) => (
              <Input
                id={id}
                type="email"
                inputMode="email"
                aria-required={required}
                value={laboratory.email}
                invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setLaboratory({ email: e.target.value })}
                onBlur={markBlurred("lab_email")}
              />
            )}
          </FormField>
        ) : null}

        {laboratoryFlow ? (
          <FormField
            label={t("wizard.details.fields.phone")}
            required
            error={
              show("lab_phone") && laboratory.phone.trim() === ""
                ? t("wizard.details.phoneRequired")
                : null
            }
          >
            {({ id, invalid, describedBy, required }) => (
              <Input
                id={id}
                type="tel"
                inputMode="tel"
                aria-required={required}
                value={laboratory.phone}
                invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setLaboratory({ phone: e.target.value })}
                onBlur={markBlurred("lab_phone")}
              />
            )}
          </FormField>
        ) : null}

        {laboratoryFlow ? (
          <FormField
            label={t("wizard.details.fields.description")}
            required
            error={
              show("lab_description") && laboratory.description.trim() === ""
                ? t("wizard.details.descriptionRequired")
                : null
            }
          >
            {({ id, invalid, describedBy, required }) => (
              <Textarea
                id={id}
                aria-required={required}
                rows={4}
                value={laboratory.description}
                invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setLaboratory({ description: e.target.value })}
                onBlur={markBlurred("lab_description")}
              />
            )}
          </FormField>
        ) : null}

        {!manufacturer ? (
          <FormField
            label={
              logisticsFlow || laboratoryFlow
                ? t("wizard.details.fields.taxIdOrReg")
                : t("wizard.details.fields.taxId")
            }
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
        ) : null}

        {manufacturer ? (
          <FormField
            label={t("wizard.details.fields.factoryAddress")}
            required
            error={
              show("actual_address") && identity.actual_address.trim() === ""
                ? t("wizard.details.factoryAddressRequired")
                : null
            }
          >
            {({ id, invalid, describedBy, required }) => (
              <Textarea
                id={id}
                aria-required={required}
                rows={2}
                value={identity.actual_address}
                invalid={invalid}
                aria-describedby={describedBy}
                trailing={<MapPinIcon size={18} />}
                onChange={(e) => setIdentity({ actual_address: e.target.value })}
                onBlur={markBlurred("actual_address")}
              />
            )}
          </FormField>
        ) : null}

        {!manufacturer && !logisticsFlow && !laboratoryFlow ? (
          <>
            <FormField
              label={t("wizard.details.fields.registrationDate")}
              required
              error={
                show("registration_date") && !dateOk
                  ? t("wizard.details.registrationDateInvalid")
                  : null
              }
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
              error={
                show("legal_form") && identity.legal_form.trim() === ""
                  ? t("wizard.details.legalFormRequired")
                  : null
              }
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
          </>
        ) : null}
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
          {logisticsFlow
            ? t("wizard.logistics.details.next")
            : laboratoryFlow
              ? t("wizard.laboratory.details.next")
              : t("common.next")}
        </Button>
      </div>
    </form>
  );
}
