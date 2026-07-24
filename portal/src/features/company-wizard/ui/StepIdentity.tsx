import { useState } from "react";

import { useTranslation } from "react-i18next";

import { JURISDICTIONS } from "@/shared/config";
import { Button, FormField, Input, Select, Tooltip } from "@/shared/ui";

import { useWizardDraft } from "../model/draftStore";
import { useEnumOptions } from "../model/useEnumOptions";
import { isTaxIdValid } from "../model/validation";

interface StepIdentityProps {
  onNext: () => void;
}

export function StepIdentity({ onNext }: StepIdentityProps) {
  const { t } = useTranslation();
  const identity = useWizardDraft((s) => s.identity);
  const setIdentity = useWizardDraft((s) => s.setIdentity);
  const jurisdictionOptions = useEnumOptions("jurisdiction", JURISDICTIONS);
  const [touched, setTouched] = useState(false);

  const taxOk = isTaxIdValid(identity);
  const showTaxError = touched && !taxOk;

  function handleNext(): void {
    setTouched(true);
    if (taxOk) onNext();
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.identity.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.identity.subtitle")}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label={t("companies.jurisdiction")} required>
          {({ id }) => (
            <Select
              id={id}
              options={jurisdictionOptions}
              value={identity.jurisdiction}
              onChange={(e) => setIdentity({ jurisdiction: e.target.value })}
            />
          )}
        </FormField>

        <FormField
          label={t("companies.taxId")}
          required
          hint={t("wizard.identity.taxIdHint")}
          error={showTaxError ? t("wizard.identity.taxIdInvalid") : null}
        >
          {({ id, invalid, describedBy }) => (
            <Input
              id={id}
              inputMode="numeric"
              value={identity.tax_id}
              invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => setIdentity({ tax_id: e.target.value.replace(/\s+/g, "") })}
              onBlur={() => setTouched(true)}
            />
          )}
        </FormField>
      </div>

      <FormField label={t("companies.legalName")}>
        {({ id }) => (
          <Input
            id={id}
            value={identity.legal_name}
            onChange={(e) => setIdentity({ legal_name: e.target.value })}
          />
        )}
      </FormField>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label={t("company.legalForm")}>
          {({ id }) => (
            <Input
              id={id}
              placeholder="ООО / ЧП / АО"
              value={identity.legal_form}
              onChange={(e) => setIdentity({ legal_form: e.target.value })}
            />
          )}
        </FormField>

        <FormField label={t("company.director")}>
          {({ id }) => (
            <Input
              id={id}
              value={identity.director_name}
              onChange={(e) => setIdentity({ director_name: e.target.value })}
            />
          )}
        </FormField>
      </div>

      <FormField label={t("company.legalAddress")}>
        {({ id }) => (
          <Input
            id={id}
            value={identity.legal_address}
            onChange={(e) => setIdentity({ legal_address: e.target.value })}
          />
        )}
      </FormField>

      <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
        <Tooltip content={t("wizard.identity.eimzoSoon")}>
          <Button variant="secondary" disabled>
            {t("wizard.identity.eimzo")}
          </Button>
        </Tooltip>
        <Button onClick={handleNext} disabled={!taxOk} className="sm:min-w-40">
          {t("common.next")}
        </Button>
      </div>
    </div>
  );
}
